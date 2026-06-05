"""
Provide class Users
"""


import http
import functools
import pathlib as pl

import mattermost

from . import dump
from .hashablematterdata import HashableMatterData


users_subdir = pl.Path('users')


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
                self._init.rate_limiter.wait()
                for user in self._init.matter.get_users_by_ids_list(list(user_ids)):
                    self._user_data[user['id']] = HashableMatterData(user)

        except mattermost.ApiException as ex:
            if ex.args[0]['status_code'] != http.HTTPStatus.REQUEST_ENTITY_TOO_LARGE:
                raise

            # split set of user IDs
            half_len = int(len(user_ids) / 2)
            second_half = user_ids.copy()
            first_half = {second_half.pop() for i in range(half_len)}

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
        """
        Convenience method to get the names of the users of a channel except
        the executing user themself

        channel: Mattermost channel

        return: set of user names
        """

        members = self.get_group_members(channel)
        return {self.get_user_data(m['user_id'])['username'] \
                for m in members if m['user_id'] != self._init.calling_user_id}

    def backup_all_users(self):
        """Backup all user data in the users data subdir"""

        if self._init.options.skip_users:
            return

        # Get IDs of all team/channel members and the executing user themself
        member_user_ids = {self._init.calling_user_id}
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
            self._init.rate_limiter.wait()
            user = self.get_user_data(user_id)
            old_user_data = dump.dump_content(
                users_dir, user, name=user["username"], return_old_content=True)

            if self._init.options.skip_user_images:
                continue

            skip_existing = False
            if old_user_data:
                current_last_picture_update = user.get(
                    'last_picture_update', 0)
                old_last_picture_update = old_user_data.get(
                    'last_picture_update', 0)
                if current_last_picture_update <= old_last_picture_update:
                    skip_existing = True

            image_loader = functools.partial(
                self._init.matter.get_user_profile_image, user_id)
            dump.dump_image(
                users_dir, user_id, image_loader,
                label=f'{user["username"]}{dump.FILENAME_SEPARATOR}image',
                skip_existing=skip_existing)

        # Newline after progress dots
        print()
