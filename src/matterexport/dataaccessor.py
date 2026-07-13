"""
Classes to access the database
"""


# pylint: disable=fixme
# TODO: resolve todos and remove this pylint exception


import sys
import pathlib as pl
import json
import datetime
import re

from matterbak import dump


class DataAccessor:
    """Main class to access stored data"""

    class InvalidPath(ValueError):
        """Exception raised when a data object cannot be found"""
        def __init__(self, path):
            self.path = path

    @staticmethod
    def get_timestamp(mattermost_timestamp):
        """Convert a Mattermost timestamp to a datatime object"""
        return datetime.datetime.fromtimestamp(mattermost_timestamp / 1000)

    def __init__(self, data_dir):
        """Init

        Args:
            data_dir: root dir of matterbak data
        """

        self.data_dir = data_dir
        self.users = Users(self.data_dir)
        # self.emojis = Emojis(self.data_dir)

    def get_team(self, identifier):
        """Get Team object for identifier"""
        return Team(self.data_dir, identifier)

    def get_channel(self, identifier):
        """Get Channel object for identifier"""
        return Channel(self.data_dir, identifier)


class Users:
    """Class to access user data

    Data is cached so it is cheap to request the same data multiple times.
    """

    def __init__(self, data_dir):
        self.users_dir = data_dir / dump.users_subdir
        if not self.users_dir.is_dir():
            print("Couldn't find directory with user data", file=sys.stderr)
            self.users_dir = None

        # Cache
        self._data = {}

    def get_data(self, user_id):
        """Get data belonging to a user ID"""
        if user_id not in self._data:
            self._data[user_id] = None
            if self.users_dir and self.users_dir.is_dir():
                for user_path in self.users_dir.iterdir():
                    if (user_path.name.startswith(user_id)
                        and user_path.suffix.lower() == dump.JSON_EXTENSION):
                        with user_path.open(encoding='utf8') as user_file:
                            user = json.load(user_file)
                        if user['id'] != user_id:
                            raise ValueError(f"User ID {user['id']} in user data"
                                             f" file does not conform to filename '{user_path}'")
                        self._data[user_id] = user
                        break

        return self._data[user_id]

    def get_given_name(self, user_id):
        """Return a user ID's first/last name or empty string"""
        user = self.get_data(user_id)
        if not user:
            return ''

        first_name = user.get('first_name', '').strip()
        last_name = user.get('last_name', '').strip()
        given_name = f"{first_name} {last_name}".strip()
        return given_name

    def get_displayname(self, user_id):
        """Return best name to display

        If availabe returns in this order:

        1. nickname
        2. first/last name
        3. username
        4. user_id
        """

        user = self.get_data(user_id)

        if not user:
            return user_id

        if nickname := user.get('nickname', ''):
            return nickname

        if given_name := self.get_given_name(user_id):
            return given_name

        return user.get('username', user_id)

    def get_image(self, user_id):
        """Return user's image file path if available else None"""
        user = self.get_data(user_id)
        if not user:
            return None

        images = self.users_dir.glob(f"{user_id}*{dump.SUFFIX_IMAGE}*")
        if len(images) > 1:
            print(f"Found multiple images for user {self.get_displayname(user_id)}, use first one")
        if images:
            return images[0]
        return None


class Emojis:
    """Get data for emojis"""

    # TODO: implement, also for unicode emojis

    # According to custom-emoji adding dialog, emoji names consist of lower-case
    # letters, numbers, and [+-_]
    emoji_re = re.compile(r':[a-z0-9_+-]+:')

    # pylint: disable=unused-argument
    def __init__(self, data_dir):
        # Cache
        self._data = {}
        raise NotImplementedError

    def get_data(self, identifier):
        """Get data belonging to a emoji ID"""
        raise NotImplementedError

    def get_image(self, identifier):
        """Get emoji image file path"""
        raise NotImplementedError



class Team:
    """Get data for a team"""

    def __init__(self, data_dir, identifier):
        """Init

        Args:
            data_dir: root dir of matterbak data
            identifier: possible team identifier, see self.get_team_dir()
        """
        self.team_dir = self.get_team_dir(data_dir, identifier)
        data_filename = self.team_dir.with_suffix(dump.JSON_EXTENSION)
        with data_filename.open(encoding='utf8') as data_file:
            self.metadata = json.load(data_file)

    @staticmethod
    def get_team_dir(data_dir, identifier):
        """Find team dir

        Args:
            identifier: Should be one of
                        1.) team ID
                        2.) internal team name
                        3.) relative or absolute path to a team data directory
                        The first found is taken.

        Raises:
            ValueError: if no channel dir could be found.
        """

        def search_dir(pattern):
            candidates = list(teams_dir.glob(pattern + '/'))
            if len(candidates) > 1:
                raise ValueError(f"Found multiple teams with ID '{identifier}'."
                                 f" Use team ID instead: {candidates}")
            if len(candidates) == 1:
                return candidates[0]
            return None

        teams_dir = data_dir / dump.teams_subdir

        # Try identifier as team ID
        # We assume that Mattermost IDs are unique over all types
        candidate = search_dir(f'{identifier}{dump.FILENAME_SEPARATOR}*')
        if candidate:
            return candidate

        # Try identifier as team name
        # TODO: look into team data and check name and display_name
        #       then adapt docs of methods, readme, etc.
        candidate = search_dir(f'*{dump.FILENAME_SEPARATOR}{identifier}')
        if candidate:
            return candidate

        # Try identifier as path
        path = pl.Path(identifier)
        if path.is_dir():
            return path

        raise ValueError(f"Cannot find team with {identifier=}")

    def get_name(self):
        """Get name to display"""
        return f"{self.metadata['display_name']} ({self.metadata['name']})"


class Channel:
    """Get data of a channel"""

    def __init__(self, data_dir, identifier):
        """Init

        Args:
            data_dir: root dir of matterbak data
            identifier: possible channel identifier, see self.get_channel_dir()
        """

        self.channel_dir = self.get_channel_dir(data_dir, identifier)
        filename = self.channel_dir.name

        data_filename = self.channel_dir.with_name(self.channel_dir.name + dump.JSON_EXTENSION)
        with data_filename.open(encoding='utf8') as data_file:
            self.metadata = json.load(data_file)

        members_filename = (self.channel_dir.parent /
                            f'{filename}{dump.FILENAME_SEPARATOR}'
                            f'{dump.SUFFIX_MEMBERS}{dump.JSON_EXTENSION}')
        if not members_filename.is_file():
            raise RuntimeError(f"Missing file with channel members data: {members_filename}")
        with members_filename.open(encoding='utf8') as members_file:
            self.members = json.load(members_file)

        threads_filename = (self.channel_dir.parent /
                            f'{filename}{dump.FILENAME_SEPARATOR}'
                            f'{dump.SUFFIX_THREADS}{dump.JSON_EXTENSION}')
        if not threads_filename.is_file():
            raise RuntimeError(f"Missing file with channel threads data: {threads_filename}")
        with threads_filename.open(encoding='utf8') as threads_file:
            self.threads = json.load(threads_file)

    def get_name(self):
        """Get display_name if present else internal name"""
        display_name = self.metadata['display_name']
        return display_name if display_name else self.metadata['name']

    @staticmethod
    def get_channel_dir(data_dir, identifier):
        """Find channel dir

        Args:
            identifier: Should be one of
                        1.) channel ID
                        2.) internal channel name
                        3.) relative or absolute path to a channel data directory
                        The first found is taken.

        Raises:
            ValueError: if no channel dir could be found.
        """

        def search_dir(pattern):
            candidates = list(data_dir.rglob(pattern + '/'))
            candidate_dirs = [ c for c in candidates if c.is_dir() ]
            if len(candidate_dirs) > 1:
                raise ValueError(f"Found multiple channels with ID '{identifier}'."
                                 f" Use channel ID instead: {candidates}")
            if len(candidate_dirs) == 1:
                return candidate_dirs[0]
            return None

        # Try identifier as channel ID
        # We assume that Mattermost IDs are unique over all types
        candidate = search_dir(f'{identifier}{dump.FILENAME_SEPARATOR}*')
        if candidate:
            return candidate

        # Try identifier as channel name
        # TODO: look into channel data and check name and display_name
        #       then adapt docs of methods, readme, etc.
        candidate = search_dir(f'*{dump.FILENAME_SEPARATOR}{identifier}')
        if candidate:
            return candidate

        # Try identifier as path
        path = pl.Path(identifier)
        if path.is_dir():
            return path

        raise ValueError(f"Cannot find channel with {identifier=}")

    def get_posts(self):
        """Generator for Post objects in chronological order"""
        post_files = list(self.channel_dir.iterdir())
        post_files.sort()

        for post_path in post_files:
            try:
                post = Post(post_path)
            except DataAccessor.InvalidPath:
                continue

            yield post

    def get_post(self, post_id):
        """Get post data"""
        paths = list(self.channel_dir.glob(f'*{post_id}{dump.JSON_EXTENSION}'))
        if len(paths) != 1:
            raise RuntimeError(f"Found {len(paths)} files for post ID {post_id}: {paths}")
        post_path = paths[0]
        return Post(post_path)

    def get_threads(self):
        """Generator for threads in chronological order

        Returns each thread as a chronological sorted list of Post objects. Threads
        are sorted by creation time of their root posts.

        Posts not belonging to a thread are inserted as single post threads.
        """
        handled_posts = set()
        for post in self.get_posts():
            post_id = post.get_id()
            if post_id in handled_posts:
                continue
            handled_posts.add(post_id)

            if post_id in self.threads:
                answer_ids = self.threads[post_id]
                handled_posts |= set(answer_ids)
                answer_posts = [ self.get_post(i) for i in answer_ids ]
                answer_posts = [post] + sorted(answer_posts, key=Post.get_timestamp)
                yield answer_posts
            else:
                yield [post]


class Post:
    """Get data of a post"""

    def __init__(self, post_path):
        """Init

        Args:
            post_path: path to post data file

        Raises:
            InvalidPath: if post_path is invalid
        """
        if post_path.suffix.lower() != dump.JSON_EXTENSION:
            raise DataAccessor.InvalidPath(post_path)

        self.post_path = post_path

        with post_path.open(encoding='utf8') as post_file:
            self.data = json.load(post_file)

    def get_id(self):
        """Return post ID"""
        return self.data['id']

    def get_timestamp(self):
        """Return creation time as datetime object"""
        return DataAccessor.get_timestamp(self.data["create_at"])

    def get_files(self):
        """Generator for files attached to the post

        Yields pairs of metadata and path to the file.
        """
        files_dir = self.post_path.parent / dump.files_subdir
        if not files_dir.is_dir():
            raise RuntimeError(f"Location for attachment files is not a directory: {files_dir}")

        for file_id in self.data['file_ids']:
            file_data_path = files_dir / f"{file_id}{dump.JSON_EXTENSION}"
            if not file_data_path.is_file():
                print("WARNING: cannot find file with data about attachment ID"
                      f" {file_id}. Skipping attachment.")
                continue

            with file_data_path.open(encoding='utf8') as file_data_file:
                file_data = json.load(file_data_file)
            if file_id != file_data['id']:
                raise ValueError(f"File ID {file_data['id']} in file data"
                                f" file does not conform to filename '{file_data_path}'")

            file_content_path = files_dir / f"{file_id}{dump.FILENAME_SEPARATOR}{file_data['name']}"
            if not file_content_path.is_file():
                file_content_path = None

            yield file_data, file_content_path

    def get_reactions(self):
        """Generator for reaction data

        Yields Mattermost reaction data objects.
        """
        if 'metadata' in self.data:
            yield from self.data['metadata'].get('reactions', [])
