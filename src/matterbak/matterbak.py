#!/usr/bin/env python3
"""
matterbak backs up all channels including direct conversations listed in a config file
"""

import argparse
import json
import os
import zipfile
import pprint
import pathlib as pl
import functools
import time
import random
import importlib.metadata

from . import dump
from .hashablematterdata import HashableMatterData
from . import teams
from . import users
from . import channeldata


# NOTE: You need to provide a fork of the mattermost package containing
#       get_teams_for_user endpoint unless the related pull request is executed
import mattermost




default_data_dir = pl.Path('data')



class RateLimiter:
    """Simple rate limiter to control API call frequency."""
    def __init__(self, calls_per_second, initial_jitter, step_jitter):
        if calls_per_second <= 0:
            self.interval = 0
        else:
            self.interval = 1.0 / calls_per_second
        self.last_call_time = 0.0

        self.initial_jitter = initial_jitter
        self.step_jitter = step_jitter

    def wait(self):
        """Wait if the rate limit is reached."""
        now = time.time()
        if now - self.last_call_time < self.interval:
            sleep_time = self.interval - (now - self.last_call_time)
            time.sleep(sleep_time)
        self.last_call_time = now

    def wait_jitter(self, initial=False):
        """Wait random initial or step jitter time"""
        jitter = self.initial_jitter if initial else self.step_jitter
        if jitter > 0:
            delay = random.uniform(0, jitter)
            label = "Initial" if initial else "Step"
            print(f"{label} random jitter: sleeping for {delay:.2f}s")
            time.sleep(delay)



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

            # Initialize RateLimiter using command line argument
            self.rate_limiter = RateLimiter(
                calls_per_second=self.options.rate_limit,
                initial_jitter=self.options.initial_jitter,
                step_jitter=self.options.step_jitter
            )

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

        self.users = users.Users(self)
        self.teams = teams.Teams(self)

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
        parser.add_argument("--update-old-posts", action="store_true", default=False,
                            help="Update also old posts in case they changed since last update")
        parser.add_argument("--skip-direct", action="store_true", default=False,
                            help="skip direct channels")
        parser.add_argument("--skip-groups", action="store_true", default=False,
                            help="skip group channels")
        parser.add_argument("--skip-teams", action="store_true", default=False,
                            help="skip team channels")
        parser.add_argument("--skip-users", action="store_true", default=False,
                            help="Skip storing personal user data (includes --skip-user-images)")
        parser.add_argument("--skip-user-images", action="store_true", default=False,
                            help="Skip storing user images")
        parser.add_argument("--skip-emojis", action="store_true", default=False,
                            help="Skip storing custom emojis")
        parser.add_argument(
            "--rate-limit", type=float, default=10,
            help="Max API calls per second. Default: %(default)s. Set to 0 to disable.")
        parser.add_argument(
            "--initial-jitter", type=float, default=0,
            help="Random delay in seconds at script start. Default: %(default)s.")
        parser.add_argument(
            "--step-jitter", type=float, default=0,
            help="Random delay in seconds between each backup unit. Default: %(default)s.")
        parser.add_argument('--version', action='version', version=importlib.metadata.version('matterbak'))
        return parser.parse_args()

    def _get_mattermost_api(self, creds):
        matter = mattermost.MMApi(creds["url"])
        if "token" in creds:
            matter.login(bearer=creds["token"])
        else:
            matter.login(creds["user"], creds["password"])
        return matter


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
            print("Dumping direct channel with "
                  f"{json.dumps(channel_username)}")
            channel_dir = init.options.data_dir / dump.direct_subdir
            channel_data = channeldata.Channel_Data(init, channel_username, dc, channel_dir)
            num_posts, num_files = channel_data.backup()
            print(f"    dumped {num_posts} posts and {num_files} files")
            configured_direct_channels.discard(channel_username)
        else:
            print(f"Skip direct channel with {json.dumps(channel_username)}")

    if(configured_direct_channels):
        print("\nConfigured but missing direct channels: "
              f"{json.dumps(sorted(configured_direct_channels))}")


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
        sorted_member_usernames = sorted(member_usernames)
        if is_backup_group_channel(member_usernames, init.channels_config):
            name = dump.filename_separator.join(sorted_member_usernames)
            print("Dumping group channel with "
                  f"{json.dumps(sorted_member_usernames)} as {name}")
            channel_dir = init.options.data_dir / dump.groups_subdir
            channel_data = channeldata.Channel_Data(init, name, gc, channel_dir)
            num_posts, num_files = channel_data.backup()
            print(f"    dumped {num_posts} posts and {num_files} files")
        else:
            print("Skip group channel with "
                  f"{json.dumps(sorted_member_usernames)}")


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
        print(f"    Not found {names_key} channel names: "
              f"{json.dumps(sorted(missing_channel_names))}")
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
        print(
            f"    {len(channel_names)}/{len(team_channels)} channels {label}: "
            f"{json.dumps(sorted(channel_names))}")

    print("\n---TEAM CHANNELS---")
    for team_name, team_config in init.channels_config.get('teams', {}).items():
        print(f"\nTeam {json.dumps(team_name)}")
        team = init.teams.get_team_by_name(team_name)
        if not team:
            print(f"    User \'{init.calling_username}\' does not have access "
                  f"to team {json.dumps(team_name)}. Skipping team.")
            continue

        team_channels = init.teams.get_team_channels(team)

        backup_team_channels = select_channels_by_names(team_channels, team_config, 'include')
        if not backup_team_channels:
            backup_team_channels = team_channels.copy()

        exclude_channels = select_channels_by_names(team_channels, team_config, 'exclude')
        backup_team_channels -= exclude_channels

        print_channels(backup_team_channels, "to backup")
        print_channels(team_channels - backup_team_channels, "skipped from backup")

        team_dir = init.options.data_dir / dump.teams_subdir
        team_dir.mkdir(parents=True, exist_ok=True)
        dump.dump_content(team_dir, team, name=team_name)

        icon_loader = functools.partial(init.matter.get_team_icon, team['id'])
        dump.dump_image(team_dir, team['id'], icon_loader, dump.suffix_icon)

        for channel in backup_team_channels:
            channel_dir = team_dir / f"{team['id']}{dump.filename_separator}{team_name}"
            print(f"    Dumping channel {json.dumps(channel['display_name'])}")

            channel_data = channeldata.Channel_Data(init, channel['name'], channel, channel_dir)
            num_posts, num_files = channel_data.backup()
            print(f"        dumped {num_posts} posts and {num_files} files")

        members = init.users.get_group_members(team)
        dump.dump_content(team_dir, members, id_=team['id'], name=f"{team_name}{dump.filename_separator}{dump.suffix_members}")


def backup_custom_emojis(init):
    """Backup all custom emojis

    init: instance of the Init class
    """

    print("\n---CUSTOM EMOJIS---")

    emojis_dir = init.options.data_dir / dump.emojis_subdir
    emojis_dir.mkdir(parents=True, exist_ok=True)

    for emoji in init.matter.get_list_of_custom_emojis():
        init.rate_limiter.wait()
        print('.', end='', flush=True)

        skip_existing = False
        old_emoji = dump.dump_content(emojis_dir, emoji, name=emoji['name'], return_old_content=True)
        if old_emoji and (emoji['update_at'] <= old_emoji['update_at']):
            skip_existing = True

        image_loader = functools.partial(init.matter.get_custom_emoji_image, emoji['id'])
        dump.dump_image(emojis_dir, emoji['id'], image_loader, label=emoji['name'], skip_existing=skip_existing)
    print()


def create_zip_file(init):
    """Store all data files in a zip file"""

    print("\n---CREATE ZIP FILE---")
    with zipfile.ZipFile(init.options.output_zip, "w") as zipf:
        for f in init.options.data_dir.glob('**/*'):
            f_without_data_dir = f.relative_to(init.options.data_dir)
            zipf.write(f, arcname=f_without_data_dir)


def main():
    """Main function, also entry point for the matterbak script"""

    try:
        init = Init()

        # Apply initial random sleep to avoid
        # for example simultaneous cron job starts
        init.rate_limiter.wait_jitter(initial=True)

        if not init.options.skip_direct:
            backup_direct_channels(init)
            # optional sleep
            init.rate_limiter.wait_jitter()

        if not init.options.skip_groups:
            backup_group_channels(init)
            # optional sleep
            init.rate_limiter.wait_jitter()

        if not init.options.skip_teams:
            backup_team_channels(init)
            # optional sleep
            init.rate_limiter.wait_jitter()

        init.users.backup_all_users()
        # optional sleep
        init.rate_limiter.wait_jitter()

        if not init.options.skip_emojis:
            backup_custom_emojis(init)
            # optional sleep
            init.rate_limiter.wait_jitter()

        create_zip_file(init)


    except mattermost.ApiException as ex:
        print(f"Error accessing Mattermost: {ex}")
        exit(1)


if __name__ == "__main__":
    main()

