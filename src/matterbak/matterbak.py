#!/usr/bin/env python3
"""
matterbak backs up all channels including direct conversations listed in a config file
"""

import argparse
import datetime
import json
import os
import zipfile
import pprint
import pathlib as pl
import http

# NOTE: You need to provide a fork of the mattermost package containing
#       get_teams_for_user endpoint unless the related pull request is executed
import mattermost


# Channel objects contain a type attribute as a single letter
CHANNEL_TYPE_DIRECT = 'D'
CHANNEL_TYPE_GROUP = 'G'
CHANNEL_TYPE_PUBLIC = 'O'
CHANNEL_TYPE_PRIVATE = 'P'
# We do not distinguish public and private team channels
CHANNEL_TYPE_TEAM = (CHANNEL_TYPE_PUBLIC, CHANNEL_TYPE_PRIVATE)


default_data_dir = pl.Path('data')
# Subdirs below data_dir to store the related downloads
users_subdir = pl.Path('users')
teams_subdir = pl.Path('teams')
groups_subdir = pl.Path('groups')
direct_subdir = pl.Path('direct')

# Separator between parts of a filename
filename_separator = '__'
# Format for timestamps in file names
timestamp_format = "%Y%m%d-%H%M%S%f"


class Init:
    """Parses the command line and provides all setup to run the downloads
    """

    def __init__(self):
        """Provide the following attributes

        options:         result of the command line parser
        channels_config: dict with the channels config file content
        matter:          logged in mattermost.MMApi instance
        username:        name of the logged in user
        user:            data of the logged in user
        user_id:         id of the logged in user
        teams:           initialized Teams object
        """

        self.options = self._parse_command_line()

        with open(self.options.credentials, encoding="utf8") as cred_file:
            creds = json.load(cred_file)
        self.username = creds["user"]
        print(f"Using user '{self.username}'")

        self.matter = self._get_mattermost_api(creds)

        if self.options.output_zip is None:
            self.options.output_zip = pl.Path(f'matterbak_{self.username}.zip')

        with open(self.options.channels, encoding="utf8") as channels_config_file:
            self.channels_config = json.load(channels_config_file)
        print(f"channels config:\n{pprint.pformat(self.channels_config)}")

        self.user = self.matter.get_user_by_username(self.username)
        self.user_id = self.user["id"]

        self.teams = Teams(self)

    def _parse_command_line(self):
        parser = argparse.ArgumentParser()
        parser.add_argument("--credentials", type=pl.Path, default=pl.Path('credentials.json'),
                            help="json file containing user name, password and server URL, default = %(default)s")
        parser.add_argument("--channels", type=pl.Path, default=pl.Path('channels.json'),
                            help="json file listing all channels to backup, default = %(default)s")
        parser.add_argument("-d", "--data-dir", type=pl.Path, default=default_data_dir,
                            help="Dir to store downloaded data in, absolute or relative to current dir, default = %(default)s")
        parser.add_argument("-o", "--output-zip", type=pl.Path, default=None,
                            help="zip file to write, default is 'matterbak_<user>.zip'")
        parser.add_argument("--skip-direct", action="store_true", default=False,
                            help="skip direct channels")
        parser.add_argument("--skip-groups", action="store_true", default=False,
                            help="skip group channels")
        parser.add_argument("--skip-teams", action="store_true", default=False,
                            help="skip team channels")
        return parser.parse_args()

    def _get_mattermost_api(self, creds):
        matter = mattermost.MMApi(creds["url"])
        if "token" in creds:
            matter.login(bearer=creds["token"])
        else:
            matter.login(creds["user"], creds["password"])
        return matter


class HashableMatterData(dict):
    """Extends the dict of a mattermost object by hash method to enable storing in a set

    This class can be initialized with the original dict of the mattermost object.
    """

    def __eq__(self, other):
        return self['id'] == other['id']

    def __hash__(self):
        return hash(self['id'])


class Teams:
    """Provider team-related data"""

    def __init__(self, init):
        self._all_teams = init.matter.get_teams_for_user(init.user_id)
        if not self._all_teams:
            print(f"User \'{init.username}\' is not member of any team. Aborting.")
            exit(1)

        # Find direct and group channels
        # We need a dummy team to get the channels
        self._all_channels_of_some_team = init.matter.get_channels_for_user(init.user_id, self._all_teams[0]["id"])

    def get_personal_channels(self, is_group):
        """Get a set of the direct or group conversation channels

        is_group: pass True to receive the group channels and True to receive the direct channels

        Returns a set of mattermost channel objects as HashableMatterData objects.
        """

        channel_type = CHANNEL_TYPE_GROUP if is_group else CHANNEL_TYPE_DIRECT
        return { HashableMatterData(c) for c in self._all_channels_of_some_team if c['type'] == channel_type }

    def get_team_by_name(self, name):
        """Return the team object with the given name as name or display_name

        Returns None of noch team with that name was found.
        """
        for t in self._all_teams:
            if name in (t['name'], t['display_name']):
                return t
        return None


def dump_content(dir, content, name=None, with_timestamp=False):
    """Helper to safe the content as JSON file

    The filename will be assembled from dir and name with current timestamp as
    prefix if with_timestamp is True and content ID as prefix (if content is a
    dict with 'id' key).

    dir:            pathlib.Path of the folder to store the file in
    name:           name (without .json extension) of the file, can be empty
    with_timestamp: set to True to prefix filename with content's creation time
    content:        data to store
    """

    # Assemble filename
    filename_parts = []
    if with_timestamp:
        now = datetime.datetime.fromtimestamp(content["create_at"] / 1000)
        filename_parts.append(now.strftime(timestamp_format))

    id_string = content.get('id') if isinstance(content, dict) else None
    if id_string:
        filename_parts.append(id_string)

    if name:
        filename_parts.append(name)

    filename = filename_separator.join(filename_parts) + '.json'

    path = dir / filename
    with open(path, "w", encoding="utf8") as dump_file:
        json.dump(content, dump_file)


def select_channels_by_names(all_channels, team_config, names_key):
    """Helper to determine the channels of a team to select

    all_channels: iterable with all channels of the team
    team_config:  config dict for the team
    names_key:    either 'include' or 'exclude'

    return: set of channels with the names given as <name_key> in the channels_config
    """
    names = set(team_config.get(names_key, []))
    channels = { c for c in all_channels if (c['display_name'] in names) or (c['name'] in names) }
    final_channel_display_names = { c['display_name'] for c in channels }
    final_channel_names = { c['name'] for c in channels }
    missing_channel_names = names - final_channel_display_names - final_channel_names
    if missing_channel_names:
        print(f"    Not found {names_key} channel names: {missing_channel_names}")
    return channels


def is_backup_group_channel(member_usernames, config):
    """Return True if a group channel with member_usernames is configured to be backed up

    The group channel config contains the keys 'exact' and 'subset'. Both can
    contain a list with lists of user names. A list of user names under 'exact'
    is a match if it is the same set as member_usernames. A list of user names
    under 'subset' is a match if the configured names are a subset of member_usernames.
    """
    config_group = config.get('groups', {})

    for group in config_group.get('exact', []):
        if member_usernames == set(group):
            return True

    for group in config_group.get('subset', []):
        if set(group) <= member_usernames:
            return True

    return False


def get_channel_members(matter, channel_id, users_cache):
    """Get all members of a channel

    matter:      logged in mattermost.MMApi instance
    channel_id:  ID of the channel whose members are requested
    users_cache: dict to cache mappings of user IDs to user data

    return: dict mapping the user IDs to user data of the channel members

    users_cache avoids requesting the user data from Mattermost if a member ID is
    already known. It will be updated with the newly found users.
    """

    members = matter.get_channel_members(channel_id)
    member_ids = { m['user_id'] for m in members }
    result = {}
    for member_id in member_ids:
        if member_id not in users_cache:
            channel_user = matter.get_user(member_id)
            channel_username = channel_user['username']
            users_cache[member_id] = channel_username
        result[member_id] = users_cache[member_id]
    return result


def get_latest_post_id(posts_dir):
    """Return latest ID of posts in posts_dir

    This function assumes that the file names begin with a timestamps, such that
    the latest post has the lexicographically highest name.

    posts_dir: pathlib.Path of a dir with json files containing posts data

    return: post ID contained in the file with the max file name or None
    """
    latest_post_file = posts_dir / ' '
    for post_file in posts_dir.iterdir():
        if post_file.suffix.lower() != '.json':
            continue
        if post_file.name > latest_post_file.name:
            latest_post_file = post_file

    if latest_post_file.exists():
        with latest_post_file.open() as post_file:
            post = json.load(post_file)
            return post.get('id')

    return None


def backup_channel(matter, name, channel, channels_dir):
    """Download channel data and all its posts and files

    matter:       logged in mattermost.MMApi instance
    name:         name for the channel data file and its subdir
    channel:      channel data
    channels_dir: pathlib.Path with the dir to store the data in
    """

    filename = f"{channel['id']}{filename_separator}{name}"
    posts_dir = channels_dir / filename
    files_dir = posts_dir / 'files'
    files_dir.mkdir(parents=True, exist_ok=True)

    dump_content(channels_dir, channel, name)

    members = list(matter.get_channel_members(channel['id']))
    dump_content(channels_dir, members, f"{filename}{filename_separator}members")

    latest_id = get_latest_post_id(posts_dir)

    num_posts = 0
    num_files = 0
    user_ids = set()
    for post in matter.get_posts_for_channel(channel["id"], after=latest_id):
        print('.', end='', flush=True)
        dump_content(posts_dir, post, with_timestamp=True)
        num_posts += 1
        user_ids.add(post['user_id'])

        for file_desc in post["metadata"].get("files", []):
            file_id = file_desc["id"]
            dump_content(files_dir, file_desc)
            file_dump_path = files_dir / f'{file_id}{filename_separator}{file_desc["name"]}'
            file_dump_path.write_bytes(matter.get_file(file_id).content)
            num_files += 1
    # Newline after progress dots
    if num_posts > 0:
        print()
    return num_posts, num_files, user_ids


def backup_direct_channels(init, users_cache):
    """Store data of configured direct channels

    init:        instance of the Init class
    users_cache: dict to cache mappings of user IDs to user data to avoid double
                 download of their data

    return: set of IDs of all backed up groups except the backup user itself

    Stores all direct channels listed under the key 'direct' in the channels config file.
    """

    print("\n---DIRECT CHANNELS---")
    all_user_ids = set()
    all_direct_channels = init.teams.get_personal_channels(is_group=False)
    configured_direct_channels = set(init.channels_config.get('direct', []))
    for dc in all_direct_channels:
        members = get_channel_members(init.matter, dc['id'], users_cache)
        # Discard user's own ID except there is no other user (messages to self)
        if len(members) > 1:
            del members[init.user_id]
        assert len(members) == 1, "A direct channel has more than one user"
        channel_user_id, channel_username = members.popitem()
        if channel_username in configured_direct_channels:
            print(f"Dumping direct channel with '{channel_username}'")
            channel_dir = init.options.data_dir / direct_subdir
            num_posts, num_files, dummy = backup_channel(init.matter, channel_username, dc, channel_dir)
            print(f"    dumped {num_posts} posts and {num_files} files")
            all_user_ids.add(channel_user_id)
            configured_direct_channels.discard(channel_username)
        else:
            print(f"Skip direct channel with '{channel_username}'")

    if(configured_direct_channels):
        print(f"\nConfigured but missing direct channels: {configured_direct_channels}")

    return all_user_ids


def backup_group_channels(init, users_cache):
    """Store data of configured group channels

    init:        instance of the Init class
    users_cache: dict to cache mappings of user IDs to user data to avoid double
                 download of their data

    return: set of IDs of all backed up groups except the backup user itself

    Stores all group channels configured under the key 'group' in the channels config file.
    See is_backup_group_channel() for the criteria.
    """

    print("\n---GROUP CHANNELS---")
    all_user_ids = set()
    all_group_channels = init.teams.get_personal_channels(is_group=True)
    for gc in all_group_channels:
        members = get_channel_members(init.matter, gc['id'], users_cache)
        del members[init.user_id]
        member_usernames = set(members.values())
        if is_backup_group_channel(member_usernames, init.channels_config):
            name = filename_separator.join(sorted(member_usernames))
            print(f"Dumping group channel with '{member_usernames}' as {name}")
            channel_dir = init.options.data_dir / groups_subdir
            num_posts, num_files, dummy = backup_channel(init.matter, name, gc, channel_dir)
            print(f"    dumped {num_posts} posts and {num_files} files")
            all_user_ids |= set(members.keys())
        else:
            print(f"Skip group channel with '{member_usernames}'")
    return all_user_ids


def backup_all_team_channels(init):
    """Store data of configured teams

    init: instance of the Init class

    return: set of IDs of all team members

    Stores the team data and calls backup_channel for all configured channels.
    The list of channels is constructed in two steps.

    1. Add the channels configured under the key 'include'. If the list is empty
       or not given take all channels of the team.
    2. Remove all channels configured under the key 'exclude'.
    """

    print("\n---TEAM CHANNELS---")
    all_user_ids = set()
    for team_name, team_config in init.channels_config.get('teams', {}).items():
        print(f"\nTeam {team_name}")
        team = init.teams.get_team_by_name(team_name)
        if not team:
            print(f"    User \'{init.username}\' does not have access to team \'{team_name}\'. Skipping team.")
            continue

        all_channels = init.matter.get_channels_for_user(init.user_id, team["id"])
        # Remove direct and group message channels
        team_channels = { HashableMatterData(c) for c in all_channels if c['type'] in CHANNEL_TYPE_TEAM }

        backup_team_channels = select_channels_by_names(team_channels, team_config, 'include')
        if not backup_team_channels:
            backup_team_channels = team_channels.copy()

        exclude_channels = select_channels_by_names(team_channels, team_config, 'exclude')
        backup_team_channels -= exclude_channels

        backup_team_channels_names = { c['display_name'] for c in backup_team_channels }
        skipped_team_channel_names = { c['display_name'] for c in team_channels } - backup_team_channels_names
        print(f"    {len(backup_team_channels_names)}/{len(team_channels)} channels to backup: {backup_team_channels_names}")
        print(f"    {len(skipped_team_channel_names)}/{len(team_channels)} channels skipped from backup: {skipped_team_channel_names}")

        team_name = team['name']
        team_dir = init.options.data_dir / teams_subdir
        team_dir.mkdir(parents=True, exist_ok=True)
        dump_content(team_dir, team, team_name)
        for channel in backup_team_channels:
            channel_dir = team_dir / f"{team['id']}{filename_separator}{team_name}"
            print(f"    Dumping channel {channel['display_name']}")
            num_posts, num_files, post_user_ids = backup_channel(init.matter, channel['name'], channel, channel_dir)
            all_user_ids |= post_user_ids
            print(f"        dumped {num_posts} posts and {num_files} files")

        members = list(init.matter.get_team_members(team["id"]))
        dump_content(team_dir, members, f"{team['id']}{filename_separator}{team_name}{filename_separator}members")
        member_ids = { m['user_id'] for m in members }
        all_user_ids |= member_ids
    return all_user_ids


def backup_users(init, all_user_ids):
    """Store user data

    init:         instance of the Init class
    all_user_ids: IDs of all user data to save
    """

    print(f"\n---BACKUP {len(all_user_ids)} USERS---")

    def get_user_data(user_ids):
        """Get user data for given user IDs

        If the list of user IDs is too long for the API we split it in half and
        try again recursively.
        """
        try:
            users = { HashableMatterData(u) for u in init.matter.get_users_by_ids_list(list(user_ids)) }

        except mattermost.ApiException as ex:
            if ex.args[0]['status_code'] != http.HTTPStatus.REQUEST_ENTITY_TOO_LARGE:
                raise

            # split set of user IDs
            half_len = int(len(user_ids) / 2)
            second_half = user_ids.copy()
            first_half = { second_half.pop() for i in range(half_len) }

            # recursively get user data for both halfs
            users = get_user_data(first_half)
            users |= get_user_data(second_half)

        return users

    all_users = get_user_data(all_user_ids)
    users_dir = init.options.data_dir / users_subdir
    users_dir.mkdir(parents=True, exist_ok=True)
    for user in all_users:
        dump_content(users_dir, user, user["username"])


def create_zip_file(init):
    """Store all data files in a zip file"""

    print("\n---CREATE ZIP FILE---")
    with zipfile.ZipFile(init.options.output_zip, "w") as zipf:
        for f in init.options.data_dir.glob('**/*'):
            zipf.write(f)


def main():
    """Main function, also entry point for the matterbak script"""

    try:
        init = Init()

        users_cache = {}
        all_user_ids = { init.user_id }

        if not init.options.skip_direct:
            all_user_ids |= backup_direct_channels(init, users_cache)

        if not init.options.skip_groups:
            all_user_ids |= backup_group_channels(init, users_cache)

        if not init.options.skip_teams:
            all_user_ids |= backup_all_team_channels(init)

        backup_users(init, all_user_ids)
        create_zip_file(init)

    except json.JSONDecodeError as ex:
        print(f"JSON structure broken (note that a common cause for a misleading message is a comma after the last element of a container): {ex}")
        exit(1)

    except mattermost.ApiException as ex:
        print(f"Error accessing Mattermost: {ex}")
        exit(1)


if __name__ == "__main__":
    main()

