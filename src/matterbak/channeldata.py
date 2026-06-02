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
        self._threads = []
        self._thread_checked_posts = set()
        threads_path = self.channels_dir / dump.make_filename(self.channel_id, name=self._threads_filename, extension='.json')
        if threads_path.is_file():
            with threads_path.open(encoding="utf8") as threads_file:
                threads_json = json.load(threads_file)
            self._threads = [ set(t) for t in threads_json ]
            for t in self._threads:
                self._thread_checked_posts |= t

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

    def _update_threads(self, post_id):
        """Update thread data with new post ID"""
        if not post_id in self._thread_checked_posts:
            thread = set()

            for thread_post in self.init.matter.get_thread(post_id, 'up'):
                thread.add(thread_post['id'])

            for thread_post in self.init.matter.get_thread(post_id, 'down'):
                if thread_post['id'] not in self._thread_checked_posts:
                    thread.add(thread_post['id'])
                else:
                    for knwon_thread in self._threads:
                        if thread_post['id'] in knwon_thread:
                            # Found an old thread the new posts belong to
                            knwon_thread |= thread
                            break
                    else:
                        # A new thread started with a single old post
                        self._threads.append(thread)
                    break
            else:
                if len(thread) > 1:
                    # Totally new thread
                    self._threads.append(thread)

            # post_id should be in thread, because of the 'up' loop
            assert post_id in thread
            self._thread_checked_posts |= thread

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
                if not old_content:
                    # We assume the thread a post belongs to cannot be changed
                    # so we only update threads if the post is entirely new
                    self._update_threads(post['id'])
            print(proggress_symbol, end='', flush=True)

        # Newline after progress dots
        print()

        threads_json = [ list(t) for t in self._threads ]
        dump.dump_content(self.channels_dir, threads_json, id_=self.channel_id, name=self._threads_filename)

        return num_posts, num_files

