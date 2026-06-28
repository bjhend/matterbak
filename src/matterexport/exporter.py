"""
Provides base class for all exporters
"""


import sys
import abc

from . import dataaccessor

class Exporter(abc.ABC):
    """Abstract base class for all exporters

    This class is a context manager to manage the exported resources properly.
    """

    def __init__(self, data_dir):
        """Init

        Args:
            data_dir: root dir of matterbak data
        """
        self.data_accessor = dataaccessor.DataAccessor(data_dir)

    @abc.abstractmethod
    def close(self):
        """Cleanup output

        Multiple calls should not harm.
        """

    def __enter__(self):
        """Enter context"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Leave context by calling close"""
        self.close()

    @abc.abstractmethod
    def channel(self, identifier, by_threads=False):
        """Implementation should export a channel with its posts and files

        The base implementation returns a dataaccessor.Channel object or exits
        if it cannot be found.

        identifier: Should be one of
                    1.) channel ID
                    2.) internal channel name
                    3.) relative or absolute path to a channel data directory
                    The first found is taken.
        by_threads: Sort output by threads if applicable
        """
        try:
            channel = self.data_accessor.get_channel(identifier)
        except ValueError as ex:
            print(ex)
            sys.exit(1)
        return channel
