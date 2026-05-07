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
import functools
from icecream import ic

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
emojis_subdir = pl.Path('emojis')
files_subdir = pl.Path('files')

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

        try:
            self.options = self._parse_command_line()

            with open(self.options.credentials, encoding="utf8") as cred_file:
                creds = json.load(cred_file)
            self.calling_username = creds["user"]
            print(f"Using user '{self.calling_username}'")

            self.matter = self._get_mattermost_api(creds)

            if self.options.output_zip is None:
                self.options.output_zip = pl.Path(f'matterbak_{self.calling_username}.zip')

            with open(self.options.channels, encoding="utf8") as channels_config_file:
                self.channels_config = json.load(channels_config_file)
            print(f"channels config:\n{pprint.pformat(self.channels_config)}")

        except json.JSONDecodeError as ex:
            print(f"JSON structure of a config file broken (note that a common cause for a "
                  f"misleading error message is a comma after the last element of a container): {ex}")
            exit(1)

        calling_user = self.matter.get_user_by_username(self.calling_username)
        self.calling_user_id = calling_user["id"]

        self.users = Users(self)
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
        parser.add_argument("--skip-user-images", action="store_true", default=False,
                            help="Skip storing user images")
        parser.add_argument("--skip-emojis", action="store_true", default=False,
                            help="Skip storing custom emojis")
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
    """Provides team-related data"""

    def __init__(self, init):
        self._init = init

        self._all_teams = self._init.matter.get_teams_for_user(init.calling_user_id)
        if not self._all_teams:
            print(f"User \'{self._init.calling_username}\' is not member of any team. Aborting.")
            exit(1)

        # Find direct and group channels
        # We need a dummy team to get the channels
        self._all_channels_of_some_team = self._init.matter.get_channels_for_user(init.calling_user_id, self._all_teams[0]["id"])

    def get_personal_channels(self, is_group):
        """Get a set of the direct or group conversation channels

        is_group: pass True to receive the group channels and True to receive the direct channels

        Returns a set of mattermost channel objects as HashableMatterData objects.
        """

        channel_type = CHANNEL_TYPE_GROUP if is_group else CHANNEL_TYPE_DIRECT
        return { HashableMatterData(c) for c in self._all_channels_of_some_team if c['type'] == channel_type }

    def get_team_channels(self, team):
        """Get a set of a team's channels the executing user has access to

        team: dict with Mattermost team data

        return: set of HashableMatterData objects with Mattermost channel data
        """
        all_channels = self._init.matter.get_channels_for_user(self._init.calling_user_id, team["id"])
        # Remove direct and group message channels
        return { HashableMatterData(c) for c in all_channels if c['type'] in CHANNEL_TYPE_TEAM }

    def get_team_by_name(self, name):
        """Return the team object with the given name as name or display_name

        Returns None of noch team with that name was found.
        """
        for t in self._all_teams:
            if name in (t['name'], t['display_name']):
                return t
        return None


class Users:
    """Manages all user data"""

    def __init__(self, init):
        self._init = init
        # Mapping of user ID on Mattermost user data
        self._user_data = {}
        # Mapping of team or channel ID on team's or channel's member list
        self._group_members = {}

    def get_user_data(self, user_id=None):
        """Get Mattermost user data of a single user

        The data is cached, so only on a cache miss the user data is requested
        from Mattermost.

        user_id: user ID or None, if None data of the executing user is returned

        return: HashableMatterData with user data from Mattermost
        """
        if not user_id:
            user_id = self._init.calling_user_id

        if user_id not in self._user_data:
            data = self._init.matter.get_user(user_id)
            self._user_data[user_id] = HashableMatterData(data)
        return self._user_data[user_id]

    def _update_user_data_recursion(self, user_ids):
        """Update user data cache for given set of user IDs

        For a large number of user IDs this is more efficient than getting user
        data for each ID individually, because it applies an API call for multiple
        user data.

        Unfortunately this API call returns with an error if too many user IDs
        are passed. In that case the list is split in half and the method calls
        itself for both halfs.
        """
        try:
            if user_ids:
                for user in self._init.matter.get_users_by_ids_list(list(user_ids)):
                    self._user_data[user['id']] = HashableMatterData(user)

        except mattermost.ApiException as ex:
            if ex.args[0]['status_code'] != http.HTTPStatus.REQUEST_ENTITY_TOO_LARGE:
                raise

            # split set of user IDs
            half_len = int(len(user_ids) / 2)
            second_half = user_ids.copy()
            first_half = { second_half.pop() for i in range(half_len) }

            # recursively update user data for both halfs
            self._update_user_data_recursion(first_half)
            self._update_user_data_recursion(second_half)

    def get_group_members(self, group):
        """Return a list of either team or channel member data

        The data is cached, so only on a cache miss the data is requested
        from Mattermost.

        group: either a team or a channel Mattermost data dict

        return: list of team or channel member data
        """
        group_id = group['id']
        if group_id not in self._group_members:
            # Is group a channel?
            if 'team_id' in group:
                members = list(self._init.matter.get_channel_members(group_id))
            else:
                members = list(self._init.matter.get_team_members(group_id))
            self._group_members[group_id] = members

        return self._group_members[group_id]

    def get_other_channel_member_names(self, channel):
        """Convenience method to get the names of the users of a channel except the executing user themself

        channel: Mattermost channel

        return: set of user names
        """

        members = self.get_group_members(channel)
        return { self.get_user_data(m['user_id'])['username'] for m in members if m['user_id'] != self._init.calling_user_id }

    def backup_all_users(self):
        """Backup all user data in the users data subdir"""

        # Get IDs of all team/channel members and the executing user themself
        member_user_ids = { self._init.calling_user_id }
        for members in self._group_members.values():
            for m in members:
                member_user_ids.add(m['user_id'])
        print(f"\n---BACKUP {len(member_user_ids)} USERS---")

        # Get all missing user data
        known_user_ids = self._user_data.keys()
        unknown_user_ids = member_user_ids - known_user_ids
        self._update_user_data_recursion(unknown_user_ids)

        # Create data dir
        users_dir = self._init.options.data_dir / users_subdir
        users_dir.mkdir(parents=True, exist_ok=True)

        # Dump all user data
        all_user_ids = member_user_ids | known_user_ids
        for user_id in all_user_ids:
            print('.', end='', flush=True)
            user = self.get_user_data(user_id)
            old_user_data = dump_content(users_dir, user, name=user["username"], return_old_content=True)

            if self._init.options.skip_user_images:
                continue

            skip_existing = False
            if old_user_data:
                current_last_picture_update = user.get('last_picture_update', 0)
                old_last_picture_update = old_user_data.get('last_picture_update', 0)
                if current_last_picture_update <= old_last_picture_update:
                    skip_existing = True

            image_loader = functools.partial(self._init.matter.get_user_profile_image, user_id)
            dump_image(users_dir, user_id, image_loader,
                       label=f'{user["username"]}{filename_separator}image',
                       skip_existing=skip_existing)

        print()


def make_filename(id_, name=None, extension='', mm_timestamp=None):
    """Make a filename for a backup file

    id_:          Mattermost ID to insert into the filename
    name:         optional name to append
    extension:    optional extension for the filename
    mm_timestamp: optional Mattermost timestamp (Unix time in milliseconds)

    return: filename
    """
    filename_parts = []
    if mm_timestamp:
        now = datetime.datetime.fromtimestamp(mm_timestamp / 1000)
        filename_parts.append(now.strftime(timestamp_format))
    filename_parts.append(id_)
    if name:
        filename_parts.append(name)

    return  filename_separator.join(filename_parts) + extension


def dump_image(dir, id_, image_loader, label=None, skip_existing=False):
    """Helper to download save an image from Mattermost

    dir:           pathlib.Path of the folder to store the image in
    id_:           Mattermost ID as prefix for the filename
    image_loader:  function returning an image Response object from Mattermost API
    label:         label to append to filename
    skip_existing: if True skip download if image file already exists
    """

    found_image_files = [ f for f in dir.glob(id_+'*') if f.suffix != '.json' ]
    if skip_existing and found_image_files:
        return

    # The new image file may have a different extension so delete all existing
    # image files.
    for image in found_image_files:
        image.unlink(missing_ok=True)

    response = image_loader()
    if not response.ok:
        return

    content_type_prefix = 'image/'
    content_type = response.headers.get('content-type', '')
    if not content_type.startswith(content_type_prefix):
        print(f"Cannot store image of type '{content_type}' for ID {id_}")
        return
    extension = '.' + content_type.removeprefix(content_type_prefix)

    path = dir / make_filename(id_=id_, name=label, extension=extension)
    path.write_bytes(response.content)


def dump_content(dir, content, id_=None, name=None, with_timestamp=False, return_old_content=False):
    """Helper to save the content as JSON file

    The filename will be assembled from dir and name with current timestamp as
    prefix if with_timestamp is True and content ID as prefix (if content is a
    dict with 'id' key).

    dir:                pathlib.Path of the folder to store the file in
    content:            data to store
    id_:                Mattermost ID to be integrated into filename, if None use
                        content['id'] instead
    name:               name (without .json extension) of the file, can be empty
    with_timestamp:     set to True to prefix filename with content's creation time
    return_old_content: if True content of file to be overwritten is returned
                        or None if there was no content file
    """

    if not id_:
        id_ = content['id']
    mm_timestamp = content["create_at"] if with_timestamp else None

    path = dir / make_filename(id_, name=name, extension='.json', mm_timestamp=mm_timestamp)

    old_content = None
    if return_old_content and path.is_file():
        with path.open(encoding="utf8") as old_file:
            old_content = json.load(old_file)

    with path.open(mode="w", encoding="utf8") as dump_file:
        json.dump(content, dump_file)

    return old_content


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
        with latest_post_file.open(encoding="utf8") as post_file:
            post = json.load(post_file)
            return post.get('id')

    return None


def backup_channel(init, name, channel, channels_dir):
    """Download channel data and all its posts and files

    init:         the Init instance
    name:         name for the channel data file and its subdir
    channel:      channel data
    channels_dir: pathlib.Path with the dir to store the data in
    """

    posts_dir = channels_dir / make_filename(channel['id'], name=name)
    files_dir = posts_dir / files_subdir
    files_dir.mkdir(parents=True, exist_ok=True)

    dump_content(channels_dir, channel, name=name)

    members = init.users.get_group_members(channel)
    dump_content(channels_dir, members, id_=channel['id'], name=f"{name}{filename_separator}members")

    latest_id = get_latest_post_id(posts_dir)

    num_posts = 0
    num_files = 0
    for post in init.matter.get_posts_for_channel(channel["id"], after=latest_id):
        print('.', end='', flush=True)
        dump_content(posts_dir, post, with_timestamp=True)
        num_posts += 1

        for file_desc in post["metadata"].get("files", []):
            file_id = file_desc["id"]
            dump_content(files_dir, file_desc)
            file_respone = init.matter.get_file(file_id)
            if file_respone.ok:
                # extension is contained in name
                file_dump_path = files_dir / make_filename(file_id, name=file_desc['name'])
                file_dump_path.write_bytes(file_respone.content)
                num_files += 1
            else:
                print(f"Cannot retrieve the file '{file_desc['name']}' posted to channel '{name}': {file_respone.text}")
    # Newline after progress dots
    if num_posts > 0:
        print()
    return num_posts, num_files


def backup_direct_channels(init):
    """Store data of configured direct channels

    init: instance of the Init class

    Stores all direct channels listed under the key 'direct' in the channels config file.
    """

    print("\n---DIRECT CHANNELS---")
    all_user_ids = set()
    all_direct_channels = init.teams.get_personal_channels(is_group=False)
    configured_direct_channels = set(init.channels_config.get('direct', []))
    for dc in all_direct_channels:
        member_names = init.users.get_other_channel_member_names(dc)
        assert len(member_names) <= 1, "A direct channel has more than one user"
        channel_username = member_names.pop() if member_names else init.users.get_user_data()['username']

        if channel_username in configured_direct_channels:
            print(f"Dumping direct channel with '{channel_username}'")
            channel_dir = init.options.data_dir / direct_subdir
            num_posts, num_files = backup_channel(init, channel_username, dc, channel_dir)
            print(f"    dumped {num_posts} posts and {num_files} files")
            configured_direct_channels.discard(channel_username)
        else:
            print(f"Skip direct channel with '{channel_username}'")

    if(configured_direct_channels):
        print(f"\nConfigured but missing direct channels: {configured_direct_channels}")


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


def backup_group_channels(init):
    """Store data of configured group channels

    init: instance of the Init class

    Stores all group channels configured under the key 'group' in the channels config file.
    See is_backup_group_channel() for the criteria.
    """

    print("\n---GROUP CHANNELS---")
    all_user_ids = set()
    all_group_channels = init.teams.get_personal_channels(is_group=True)
    for gc in all_group_channels:
        member_usernames = init.users.get_other_channel_member_names(gc)
        if is_backup_group_channel(member_usernames, init.channels_config):
            name = filename_separator.join(sorted(member_usernames))
            print(f"Dumping group channel with '{member_usernames}' as {name}")
            channel_dir = init.options.data_dir / groups_subdir
            num_posts, num_files = backup_channel(init, name, gc, channel_dir)
            print(f"    dumped {num_posts} posts and {num_files} files")
        else:
            print(f"Skip group channel with '{member_usernames}'")


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


def backup_team_channels(init):
    """Store data of configured teams

    init: instance of the Init class

    Stores the team data and calls backup_channel for all configured channels.
    The list of channels is constructed in two steps.

    1. Add the channels configured under the key 'include'. If the list is empty
       or not given take all channels of the team.
    2. Remove all channels configured under the key 'exclude'.
    """

    def print_channels(channels, label):
        channel_names = { c['display_name'] for c in channels }
        print(f"    {len(channel_names)}/{len(team_channels)} channels {label}: {channel_names}")

    print("\n---TEAM CHANNELS---")
    for team_name, team_config in init.channels_config.get('teams', {}).items():
        print(f"\nTeam '{team_name}'")
        team = init.teams.get_team_by_name(team_name)
        if not team:
            print(f"    User \'{init.calling_username}\' does not have access to team \'{team_name}\'. Skipping team.")
            continue

        team_channels = init.teams.get_team_channels(team)

        backup_team_channels = select_channels_by_names(team_channels, team_config, 'include')
        if not backup_team_channels:
            backup_team_channels = team_channels.copy()

        exclude_channels = select_channels_by_names(team_channels, team_config, 'exclude')
        backup_team_channels -= exclude_channels

        print_channels(backup_team_channels, "to backup")
        print_channels(team_channels - backup_team_channels, "skipped from backup")

        team_dir = init.options.data_dir / teams_subdir
        team_dir.mkdir(parents=True, exist_ok=True)
        dump_content(team_dir, team, name=team_name)

        icon_response = init.matter.get_team_icon(team['id'])
        dump_image(team_dir, team['id'], icon_response, 'icon')

        for channel in backup_team_channels:
            channel_dir = team_dir / f"{team['id']}{filename_separator}{team_name}"
            print(f"    Dumping channel '{channel['display_name']}'")
            num_posts, num_files = backup_channel(init, channel['name'], channel, channel_dir)
            print(f"        dumped {num_posts} posts and {num_files} files")

        members = init.users.get_group_members(team)
        dump_content(team_dir, members, id_=team['id'], name=f"{team_name}{filename_separator}members")


def backup_custom_emojis(init):
    """Backup all custom emojis

    init: instance of the Init class
    """

    print("\n---CUSTOM EMOJIS---")

    emojis_dir = init.options.data_dir / emojis_subdir
    emojis_dir.mkdir(parents=True, exist_ok=True)

    for emoji in init.matter.get_list_of_custom_emojis():
        print('.', end='', flush=True)

        skip_existing = False
        old_emoji = dump_content(emojis_dir, emoji, name=emoji['name'], return_old_content=True)
        if old_emoji and (emoji['update_at'] <= old_emoji['update_at']):
            skip_existing = True

        image_loader = functools.partial(init.matter.get_custom_emoji_image, emoji['id'])
        dump_image(emojis_dir, emoji['id'], image_loader, label=emoji['name'], skip_existing=skip_existing)
    print()


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

        if not init.options.skip_direct:
            backup_direct_channels(init)

        if not init.options.skip_groups:
            backup_group_channels(init)

        if not init.options.skip_teams:
            backup_team_channels(init)

        init.users.backup_all_users()

        if not init.options.skip_emojis:
            backup_custom_emojis(init)

        create_zip_file(init)


    except mattermost.ApiException as ex:
        print(f"Error accessing Mattermost: {ex}")
        exit(1)


if __name__ == "__main__":
    main()

