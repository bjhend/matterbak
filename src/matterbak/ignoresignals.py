"""
A simple class to temporarily ignore specific signals (e.g., SIGINT, SIGTERM)
during critical operations like file writing.
"""

import os
import signal


class IgnoreSignals():
    def __init__(
            self, signals, print_message_on_signal=None, ignore_on_init=True,
            call_default_handler_after_revert=True):
        """
        Temporarily ignore specified signals (e.g., Ctrl+C, kill) during
        critical operations.

        Example:

        >>> ignore_signals = IgnoreSignals([signal.SIGINT, signal.SIGTERM])
        >>> # do critical work like file writing ...
        >>> ignore_signals.revert()

        signals (list): List of signal numbers to ignore
                        (e.g., [signal.SIGINT, signal.SIGTERM]).
        print_message_on_signal (str or callable or None):
            message to be printed on signal
            * If None (default) the f-string
              f'ignoring signal {signum} until write is finished'
              is used.
            * If a callable (e.g. lambda function):
              called with (signum, frame). This function could print other
              messages build with input.
            * If bool(print_message_on_signal) is True
              the variable print_message_on_signal is printed.
            * Otherwise (e. g. False or '') no output.
        ignore_on_init (bool): to ignore signals immediately after creation
        call_default_handler_after_revert:
            If True the default handler will be called just after reverting

        return: dict with actual handlers
        """
        self.signals = signals
        self.print_message_on_signal = print_message_on_signal
        self.default_handlers = []
        self.update_default_handlers()
        self.handler_ignored = None
        self.call_default_handler_after_revert = \
            call_default_handler_after_revert

        if ignore_on_init:
            self.ignore()

    def update_default_handlers(self):
        """
        store actual signal handlers as default handlers
        """
        self.default_handlers = []
        for sig in self.signals:
            self.default_handlers.append([sig, signal.getsignal(sig)])

    def ignore(self):
        """
        set signal handlers to ignore the signals
        """
        for sig in self.signals:
            signal.signal(sig, self.ignoring_handler)

    def revert(self):
        """
        revert/restore to original/default signal handlers

        More precisely the signal handlers defined during
        class instance creation
        or calling the method `update_default_handlers`
        """
        for (sig, handler) in self.default_handlers:
            signal.signal(sig, handler)
        if self.handler_ignored is not None:
            os.kill(os.getpid(), self.handler_ignored)
            self.handler_ignored = None

    def ignoring_handler(self, signum, frame):
        """
        handler that ignores the signal and optionally prints a message
        or calls a function
        """
        self.handler_ignored = signum
        if self.print_message_on_signal is None:
            print(f'ignoring signal {signum} until write is finished')
        if callable(self.print_message_on_signal):
            self.print_message_on_signal(signum, frame)
        elif self.print_message_on_signal:
            print(self.print_message_on_signal)
