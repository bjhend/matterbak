"""
Exporter creating Markdown output
"""


import sys
import pprint

from .exporter import Exporter
from . import dataaccessor


class Markdown_Exporter(Exporter):
    """Exporter creating Markdown output"""

    def __init__(self, data_dir, output=None):
        """Init

        Exits if output cannot be created.

        Args:
            data_dir: root dir of matterbak data
            output:   file to write output into, if None output goes to stdout
        """
        super().__init__(data_dir)

        if not output:
            self.output = sys.stdout
        else:
            try:
                self.output = open(output, 'w')
            except OSError as ex:
                print(f"Cannot open {output} as output file: {ex}")
                exit(1)

    def close(self):
        """Close output file if applicable"""
        if sys.stdout != self.output:
            self.output.close()

    def _append_output(self, text):
        """Append a line of text to output"""
        print(text, file=self.output)

    def _append_post(self, post, heading='###'):
        """Append post data to output

        Args:
            post:    dataaccessor.Post object
            heading: heading marker for title
        """
        timestamp = post.get_timestamp()
        username = self.users.get_displayname(post.data['user_id'])

        # TODO: get custom emojis from metadata?
        # TODO: replace in-text emoji names by images?
        self._append_output(f"{heading} {username} at {timestamp.replace(microsecond=0)}\n{post.data['message']}\n")

        any_file = False
        for file_data, file_content_path in post.get_files():
            if not any_file:
                self._append_output("Files:\n")
                any_file = True
            self._append_output(f"* {file_data['name']}: `{file_content_path}`")
        if any_file:
            self._append_output('')

        any_reaction = False
        for reaction in post.get_reactions():
            if not any_reaction:
                self._append_output("Reactions:\n")
                any_reaction = True
            username = self.users.get_displayname(reaction['user_id'])
            # TODO: insert emoji image
            self._append_output(f"* {username}: `{reaction['emoji_name']}`")
        if any_reaction:
            self._append_output('')

    def channel(self, identifier, by_threads=False):
        """Exporter for a channel, implementation for Exporter.channel()"""

        channel = super().channel(identifier, by_threads)

        # TODO: print only meaningful meta data and members
        # TODO: print team data and icon

        self._append_output(f"# {channel.get_name()}\n")
        self._append_output(f"{channel.metadata['header']}\n")
        self._append_output(f"{channel.metadata['total_msg_count']} messages in {channel.metadata['total_msg_count_root']} threads or single messages\n")

        self._append_output("## Metadata\n")
        self._append_output(pprint.pformat(channel.metadata))

        self._append_output("## Members\n")
        self._append_output(pprint.pformat(channel.members))

        self._append_output("## Messages\n")

        if not by_threads:
            for post in channel.get_posts():
                self._append_post(post)
        else:
            for thread in channel.get_threads():
                self._append_output(f"### Thread")
                for post in thread:
                    self._append_post(post, heading='####')


