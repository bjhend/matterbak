"""
Exporter creating format conforming to HGF exporter format

See https://codebase.helmholtz.cloud/helmholtz-matrix/mattermost-archiver-plugin
"""


import pathlib as pl
import tempfile
import json
import zipfile
import shutil
import datetime

from .exporter import Exporter



class HgfExporter(Exporter):
    """Exporter creating Markdown output"""

    _post_keys = [
        'id',
        'channel_id',
        'user_id',
        'user_username',
        'user_display_name',
        'create_at',
        'update_at',
        'delete_at',
        'message',
        'type',
        'root_id',
        'file_ids',
        'props',
        'hashtags',
        # 'metadata',
    ]

    def __init__(self, data_dir, output):
        super().__init__(data_dir)
        if not output:
            raise ValueError("--output is required")
        self.output = pl.Path(output)

    def close(self):
        ...

    def _create_zip_file(self, temp_dir):
        """Store all data files in a zip file"""

        with zipfile.ZipFile(self.output, "w") as zipf:
            for name in temp_dir.glob('**'):
                if name.is_file():
                    arc_name = name.relative_to(temp_dir)
                    zipf.write(name, arc_name)

    def _make_user_displayname(self, user_id):
        user = self.data_accessor.users.get_data(user_id)
        if not user:
            return "Unknown"

        if given_name := self.data_accessor.users.get_given_name(user_id):
            return given_name
        if username := user.get('username'):
            return username
        return "Unknown"

    def _make_post_data(self, post):
        data = post.data
        user_id = data['user_id']
        data['user_username'] = self.data_accessor.users.get_data(user_id)['username']
        data['user_display_name'] = self._make_user_displayname(user_id)

        data_out = {}
        for key in self._post_keys:
            data_out[key] = data[key]

        return data_out

    def _dump_data(self, temp_dir, name, data):
        path = temp_dir / f"{name}.json"
        with path.open(mode='w', encoding='utf8') as data_file:
            json.dump(data, data_file, indent=2, ensure_ascii=False)

    def _export_posts(self, temp_dir, channel):
        posts = []
        for post in channel.get_posts():
            data = self._make_post_data(post)
            posts.append(data)
            for file_data, path in post.get_files():
                file_id = file_data['id']
                name = file_data['name']
                dest = temp_dir / 'files' / f"{file_id}-{name}"
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(path, dest)
        posts.reverse()
        self._dump_data(temp_dir, 'posts', posts)

    def _export_threads(self, temp_dir, channel):
        threads = []
        for posts in channel.get_threads():
            data = {}
            root_post = posts.pop(0)
            data['root_id'] = root_post.get_id()
            data['root'] = self._make_post_data(root_post)
            if posts:
                data['replies'] = [ self._make_post_data(reply) for reply in posts ]
            threads.append(data)
        self._dump_data(temp_dir, 'threads', threads)

    def _create_skipped_attachments(self, temp_dir):
        now = datetime.datetime.utcnow().replace(microsecond=0)
        skipped_attachments = {
                'generated_at': now.isoformat(),
                'omitted_count': 0,
                'omitted_total': "0 B",
                'max_per_file': "0 B",
                'attachments': [],
            }
        self._dump_data(temp_dir, 'skipped_attachments', skipped_attachments)

    def channel(self, identifier, by_threads=False):
        channel = self.data_accessor.get_channel(identifier)

        with tempfile.TemporaryDirectory(prefix='matterexport-hgf_') as temp_dir_name:
            temp_dir = pl.Path(temp_dir_name)

            self._dump_data(temp_dir, 'channel', channel.metadata)
            self._export_posts(temp_dir, channel)
            self._export_threads(temp_dir, channel)
            self._create_skipped_attachments(temp_dir)

            self._create_zip_file(temp_dir)
