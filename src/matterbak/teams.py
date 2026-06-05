"""
Provide class Teams
"""


from .hashablematterdata import HashableMatterData

# Channel objects contain a type attribute as a single letter
CHANNEL_TYPE_DIRECT = 'D'
CHANNEL_TYPE_GROUP = 'G'
CHANNEL_TYPE_PUBLIC = 'O'
CHANNEL_TYPE_PRIVATE = 'P'
# We do not distinguish public and private team channels
CHANNEL_TYPE_TEAM = (CHANNEL_TYPE_PUBLIC, CHANNEL_TYPE_PRIVATE)


class Teams:
    """Provides team-related data"""

    def __init__(self, init):
        self._init = init

        self._all_teams = self._init.matter.get_teams_for_user(
            init.calling_user_id)
        if not self._all_teams:
            print(
                f"User \'{self._init.calling_username}\' is not member of any team. Aborting.")
            exit(1)

        # Find direct and group channels
        # We need a dummy team to get the channels
        self._all_channels_of_some_team = self._init.matter.get_channels_for_user(
            init.calling_user_id, self._all_teams[0]["id"])

    def get_personal_channels(self, is_group):
        """Get a set of the direct or group conversation channels

        is_group: pass True to receive the group channels and True to receive the direct channels

        Returns a set of mattermost channel objects as HashableMatterData objects.
        """

        channel_type = CHANNEL_TYPE_GROUP if is_group else CHANNEL_TYPE_DIRECT
        return {HashableMatterData(c) \
                for c in self._all_channels_of_some_team \
                if c['type'] == channel_type}

    def get_team_channels(self, team):
        """Get a set of a team's channels the executing user has access to

        team: dict with Mattermost team data

        return: set of HashableMatterData objects with Mattermost channel data
        """
        all_channels = self._init.matter.get_channels_for_user(
            self._init.calling_user_id, team["id"])
        # Remove direct and group message channels
        return {HashableMatterData(c) for c in all_channels if c['type'] in CHANNEL_TYPE_TEAM}

    def get_team_by_name(self, name):
        """Return the team object with the given name as name or display_name

        Returns None of noch team with that name was found.
        """
        for t in self._all_teams:
            if name in (t['name'], t['display_name']):
                return t
        return None
