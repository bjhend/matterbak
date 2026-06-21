"""
Interface to Mattermost API
"""


import mattermost


# Pass through mattermost.ApiException
ApiException = mattermost.ApiException


class MattermostApi:
    """Extension of mattermost package with additional functions

    When a Mattermost API function is called as a method of this class it is
    first searched in this class and if not found the call is passed to
    the mattermost package.
    """

    def __init__(self, credentials):
        """Init connection to Mattermost API with given credentials"""
        self.matter = mattermost.MMApi(credentials["url"])
        if "token" in credentials:
            self.matter.login(bearer=credentials["token"])
        else:
            self.matter.login(credentials["user"], credentials["password"])

    def __getattr__(self, name):
        """Pass method call to mattermost.MMApi"""
        return self.matter.__getattribute__(name)

    def __dir__(self):
        """Required for extended attribute access

        Returns:
            Attribute names of this class and self.matter
        """
        return set(dir(self.matter)) | set(self.__class__.__dict__.keys())

    def get_teams_for_user(self, user_id, **kwargs):
        """
        Generator: Get a user's teams

        Args:
            team_id (string): team to get channels from.

        Returns:
            generates: Team.

        Raises:
            ApiException: Passed on from lower layers.
        """
        yield from self.matter._get("/v4/users/"+user_id+"/teams", **kwargs)

    def get_user_profile_image(self, user_id, **kwargs):
        """
        Get profile image of a user.

        Args:
            user_id (string): User whose image is requested

        Returns:
            requests.Response object, see class description how to handle it

        Raises:
            ApiException: Passed on from lower layers.
        """
        return self._get("/v4/users/"+user_id+"/image", raw=True, **kwargs)

    def get_team_icon(self, team_id, **kwargs):
        """
        Get a team's icon if present

        Args:
            team_id (string): team_id to get icon for

        Returns:
            requests.Response object, see class description how to handle it
        """
        return self._get("/v4/teams/"+team_id+"/image", raw=True, **kwargs)

    def get_posts_for_channel(self, channel_id, after=None, before=None, **kwargs):
        """
        Generator: Get a page of posts in a channel. Use the query parameters to
        modify the behaviour of this endpoint.

        Args:
            channel_id (string): The channel ID to iterate over.
            after (string, optional): A post id to select the posts that came after this one
            before (string, optional): A post id to select the posts that came before this one

        Returns:
            generates: Post.

        Raises:
            ApiException: Passed on from lower layers.
        """
        page = 0
        while True:
            data_page = self._get("/v4/channels/"+channel_id+"/posts",
                                  params={"page":str(page), "after":after, "before":before},
                                  **kwargs)

            if data_page["order"] == []:
                break
            page += 1

            for order in data_page["order"]:
                yield data_page["posts"][order]

    def get_list_of_custom_emojis(self, **kwargs):
        """
        Generator: Get an iterator returning all custom emojis

        Returns:
            generates: Emoji

        Raises:
            ApiException: Passed on from lower layers.
        """

        page = 0
        while True:
            emojis_page = self._get("/v4/emoji", params={"page":str(page)}, **kwargs)

            if not emojis_page:
                break

            yield from emojis_page

            page += 1

    def get_custom_emoji_image(self, emoji_id, **kwargs):
        """
        Get emoji image.

        Args:
            emoji_id (string): Emoji whose image is requested

        Returns:
            requests.Response object, see class description how to handle it

        Raises:
            ApiException: Passed on from lower layers.
        """
        return self._get("/v4/emoji/"+emoji_id+"/image", raw=True, **kwargs)
