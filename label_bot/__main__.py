"""Main."""
import asyncio
import aiohttp
import os
import sys
import cachetools
import traceback
import yaml
import base64
from aiohttp import web
from gidgethub import routing, sansio
from gidgethub import aiohttp as gh_aiohttp
from . import wip_labels
from . import wildcard_labels
from . import label_mgr
from . import triage_labels
from . import review_labels
try:
    from yaml import CLoader as Loader
except ImportError:
    from yaml import Loader

__version__ = '1.0.0'

router = routing.Router()
routes = web.RouteTableDef()
cache = cachetools.LRUCache(maxsize=500)


async def get_config(gh, event, ref='master'):
    """Get label configuration file."""

    try:
        result = await gh.getitem(
            event.data['repository']['contents_url'] + '{?ref}',
            {
                'path': '.github/labels.yml',
                'ref': ref
            }
        )
        content = base64.b64decode(result['content']).decode('utf-8')
        config = yaml.load(content, Loader=Loader)
    except Exception:
        traceback.print_exc(file=sys.stdout)
        config = {}

    return config


@router.register("pull_request", action="labeled")
async def pull_labeled(event, gh, *args, **kwargs):
    """Handle pull request labeled event."""

    config = await get_config(gh, event, event.data['pull_request']['head']['sha'])
    await wip_labels.wip(event, gh, config)


@router.register("pull_request", action="unlabeled")
async def pull_unlabeled(event, gh, *args, **kwargs):
    """Handle pull request unlabeled event."""

    config = await get_config(gh, event, event.data['pull_request']['head']['sha'])
    await wip_labels.wip(event, gh, config)


@router.register("pull_request", action="reopened")
async def pull_reopened(event, gh, *args, **kwargs):
    """Handle pull reopened events."""

    config = await get_config(gh, event, event.data['pull_request']['head']['sha'])
    await wip_labels.wip(event, gh, config)
    await wildcard_labels.wildcard_labels(event, gh, config)
    await review_labels.review(event, gh, config)


@router.register("pull_request", action="opened")
async def pull_opened(event, gh, *args, **kwargs):
    """Handle pull opened events."""

    config = await get_config(gh, event, event.data['pull_request']['head']['sha'])
    await wip_labels.wip(event, gh, config)
    await wildcard_labels.wildcard_labels(event, gh, config)
    await review_labels.review(event, gh, config)


@router.register("pull_request", action="synchronize")
async def pull_synchronize(event, gh, *args, **kwargs):
    """Handle pull synchronization events."""

    config = await get_config(gh, event, event.data['pull_request']['head']['sha'])
    await wip_labels.wip(event, gh, config)
    await wildcard_labels.wildcard_labels(event, gh, config)
    await review_labels.review(event, gh, config)


@router.register("issues", action="opened")
async def issues_opened(event, gh, *args, **kwargs):
    """Handle issues open events."""

    config = await get_config(gh, event)
    await triage_labels.triage(event, gh, config)


@router.register('push', ref='refs/heads/master')
async def push(event, gh, *args, **kwargs):
    """Handle push events on master."""

    config = await get_config(gh, event, event.data['after'])
    await label_mgr.manage(event, gh, config)


@routes.post("/")
async def main(request):
    """Handle requests."""

    try:
        # Get payload
        payload = await request.read()

        # Get authentication
        secret = os.environ.get("GH_SECRET")
        token = os.environ.get("GH_AUTH")
        bot = os.environ.get("GH_BOT")
        event = sansio.Event.from_http(request.headers, payload, secret=secret)

        # Handle ping
        if event.event == "ping":
            return web.Response(status=200)

        async with aiohttp.ClientSession() as session:
            gh = gh_aiohttp.GitHubAPI(session, bot, oauth_token=token, cache=cache)

            await asyncio.sleep(1)
            await router.dispatch(event, gh)

        return web.Response(status=200)
    except Exception:
        traceback.print_exc(file=sys.stderr)
        return web.Response(status=500)


if __name__ == "__main__":
    app = web.Application()
    app.add_routes(routes)
    port = os.environ.get("PORT")
    if port is not None:
        port = int(port)

    web.run_app(app, port=port)
