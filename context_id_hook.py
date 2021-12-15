from aiohttp import web, web_log
from contextvars import ContextVar
from contextlib import ExitStack
import logging


_hook_var = ContextVar('request_id')
_hook_last_request_id = 0


def setup():
    if getattr(logging, 'request_id_log_record_factory_set_up', False):
        return
    logging.request_id_log_record_factory_set_up = True

    factory = logging.getLogRecordFactory()

    def _context_id_hook_factory(*args, **kwargs):
        record = factory(*args, **kwargs)
        req_id = _hook_var.get(None)
        record.requestIdPrefix = f'[{req_id}]' if req_id else '?'
        return record

    logging.setLogRecordFactory(_context_id_hook_factory)


class AccessLogClass(web_log.AccessLogger):
    def log(self, request, response, time):
        token = _hook_var.set(request.get("request_id"))
        try:
            super().log(request, response, time)
        finally:
            _hook_var.reset(token)


@web.middleware
async def middleware(request, handler):
    global _hook_last_request_id
    _hook_last_request_id += 1
    new_request_id = _hook_last_request_id
    request['request_id'] = new_request_id
    token = _hook_var.set(new_request_id)
    try:
        with ExitStack():
            mapping = handler.__dict__.get('__rororo_openapi_mapping__')
            if mapping:
                logging.getLogger("MAPPED").info(str(mapping.get("*")))
            else:
                logging.getLogger("UNMAPPED").info(f'{handler.__module__}:{handler.__name__}')
            return await handler(request)
    finally:
        _hook_var.reset(token)
