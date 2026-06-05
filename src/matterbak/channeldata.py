"""
Provide class Channel_Data
"""



import pathlib as pl
import json
import time
from . import dump


files_subdir = pl.Path('files')



class Channel_Data:
    """Class to store channel data and back it up"""

    def __init__(self, init, name, channel, channels_dir):
        """Init

        init:         the Init instance
        name:         name for the channel data file and its subdir
        channel:      channel data
        channels_dir: pathlib.Path with the dir to store the data in
        """
        self.init = init
        self.name = name
        self.channel = channel
        self.channel_id = self.channel['id']
        self.channels_dir = channels_dir
        self._threads_filename = f"{self.name}{dump.filename_separator}threads"
        self.posts_dir = self.channels_dir / dump.make_filename(self.channel_id, name=self.name)
        self.files_dir = self.posts_dir / files_subdir
        self.files_dir.mkdir(parents=True, exist_ok=True)
        self._load_threads()

    def _get_latest_post_id(self):
        """Return latest ID of posts in posts_dir

        This function assumes that the file names begin with a timestamps, such that
        the latest post has the lexicographically highest name.

        posts_dir: pathlib.Path of a dir with json files containing posts data

        return: post ID contained in the file with the max file name or None
        """
        latest_post_file = self.posts_dir / ' '
        for post_file in self.posts_dir.iterdir():
            if post_file.suffix.lower() != '.json':
                continue
            if post_file.name > latest_post_file.name:
                latest_post_file = post_file

        if latest_post_file.exists():
            with latest_post_file.open(encoding="utf8") as post_file:
                post = json.load(post_file)
                return post.get('id')

        return None

    def _load_threads(self):
        """Load thread data from backup"""
        self._threads = {}
        threads_path = self.channels_dir / dump.make_filename(self.channel_id, name=self._threads_filename, extension='.json')
        if threads_path.is_file():
            with threads_path.open(encoding="utf8") as threads_file:
                threads_json = json.load(threads_file)
            # Has the file the new format with root_ids as keys?
            # (The old file contained a list of lists.)
            # If not ignore loaded file. It will be overwritten with the new format.
            if dict == type(threads_json):
                self._threads = { root_id: set(post_ids) for root_id, post_ids in threads_json.items() }

    def _save_post(self, post):
        """Backup a post and its files"""
        num_files = 0
        for file_desc in post["metadata"].get("files", []):
            file_id = file_desc["id"]
            dump.dump_content(self.files_dir, file_desc)
            file_respone = self.init.matter.get_file(file_id)
            if file_respone.ok:
                # extension is contained in name
                file_dump_path = self.files_dir / dump.make_filename(file_id, name=file_desc['name'])
                file_dump_path.write_bytes(file_respone.content)
                num_files += 1
            else:
                print(f"Cannot retrieve the file '{file_desc['name']}' posted to channel '{self.name}': {file_respone.text}")
        return num_files

    def _update_threads(self, post):
        """Update thread data with new post"""
        root_id = post['root_id']
        if root_id:
            if root_id not in self._threads:
                self._threads[root_id] = set()
            self._threads[root_id].add(post['id'])

    def backup(self):
        """Download channel data and all its posts and files"""

        dump.dump_content(self.channels_dir, self.channel, name=self.name)

        members = self.init.users.get_group_members(self.channel)
        dump.dump_content(self.channels_dir, members, id_=self.channel_id, name=f"{self.name}{dump.filename_separator}members")

        if self.init.options.update_old_posts:
            latest_id = None
        else:
            latest_id = self._get_latest_post_id()

        num_posts = 0
        num_files = 0
        for post in self.init.matter.get_posts_for_channel(self.channel_id, after=latest_id):
            self.init.rate_limiter.wait()
            proggress_symbol = '.'
            old_content = dump.dump_content(self.posts_dir, post, with_timestamp=True, return_old_content=True)
            if (not old_content) or (old_content['update_at'] < post['update_at']):
                proggress_symbol = '+'
                num_posts += 1
                num_files += self._save_post(post)

            # We update the threads in any case although thread relations cannot be changed
            # because this will update the thread file format.
            self._update_threads(post)

            print(proggress_symbol, end='', flush=True)

        # Newline after progress dots
        print()

        threads_json = { root_id: list(post_ids) for root_id, post_ids in self._threads.items() }
        dump.dump_content(self.channels_dir, threads_json, id_=self.channel_id, name=self._threads_filename)

        return num_posts, num_files
