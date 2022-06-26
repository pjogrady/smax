#

import asyncio
import os
import queue
import select
import smax
import time

import smax.log as log

class AsyncioReactor(smax.Reactor):
    update = b'U'
    def __init__(self, event_loop):
        self._signal_queue = asyncio.Queue()
        self._event_loop = event_loop
        super(AsyncioReactor, self).__init__()
    async def run(self):
        while True:
            timeout = self.sync()
            if self.done():
                return
            # timeout may be None
            log.trace("timeout=%s." % timeout)
            try:
                msg = await asyncio.wait_for(self._signal_queue.get(), timeout)
            except asyncio.exceptions.TimeoutError:
                pass
    def _signal(self):
        self._signal_queue.put_nowait(self.update)
    def _run_event(self, machine, ev):
        future = self._event_loop.create_future()
        self.call(self._do_run_event, future, machine, ev)
        return future
    def _do_run_event(self, future, machine, ev):
        try:
            r = ev(machine)
            future.set_result(r)
        except Exception as e:
            future.set_exception(e)