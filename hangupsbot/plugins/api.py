from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs
from threading import Thread
from hangups.ui.utils import get_conv_name
from commands import command
from random import randrange

import json
import ssl
import asyncio
import logging
import hangups
import time

def _initialise(Handlers, bot):
    if bot:
        _start_api(bot)
    else:
        print("API could not be initialized.")
    return []

""" API plugin for listening for server commands and treating them as ConversationEvents
config.json will have to be configured as follows:

"api": [{
  "certfile": null,
  "name": SERVER_NAME,
  "port": LISTENING_PORT,
}]

"""

class ConversationEvent(object):
    """Fake Conversation event"""
    def __init__(self):
        self.conv_event = None
        self.conv_id = None
        self.conv = None
        self.event_id = None
        self.user_id = None
        self.user = None
        self.timestamp = None
        self.text = None

    def print_debug(self):
        """Print informations about conversation event"""
        print(_('eid/dtime: {}/{}').format(self.event_id, self.timestamp.astimezone(tz=None).strftime('%Y-%m-%d %H:%M:%S')))
        print(_('cid/cname: {}/{}').format(self.conv_id, get_conv_name(self.conv, truncate=True)))
        if(self.user_id.chat_id == self.user_id.gaia_id):
            print(_('uid/uname: {}/{}').format(self.user_id.chat_id, self.user.full_name))
        else:
            print(_('uid/uname: {}!{}/{}').format(self.user_id.chat_id, self.user_id.gaia_id, self.user.full_name))
        print(_('txtlen/tx: {}/{}').format(len(self.text), self.text))
        print(_('eventdump: completed --8<--'))

def _start_api(bot):
    # Start and asyncio event loop
    loop = asyncio.get_event_loop()

    api = bot.get_config_option('api')
    itemNo = -1
    threads = []

    if isinstance(api, list):
        for sinkConfig in api:
            itemNo += 1

            try:
                certfile = sinkConfig["certfile"]
                if not certfile:
                    print(_("config.api[{}].certfile must be configured").format(itemNo))
                    continue
                name = sinkConfig["name"]
                port = sinkConfig["port"]
            except KeyError as e:
                print(_("config.api[{}] missing keyword").format(itemNo), e)
                continue

            # start up api listener in a separate thread
            print("Starting API on https://{}:{}/".format(name, port))
            t = Thread(target=start_listening, args=(
              bot,
              loop,
              name,
              port,
              certfile))

            t.daemon = True
            t.start()

            threads.append(t)

    message = _("_start_api(): {} api started").format(len(threads))
    logging.info(message)

def start_listening(bot, loop=None, name="", port=8007, certfile=None):
    webhook = webhookReceiver

    if loop:
        asyncio.set_event_loop(loop)

    if bot:
        webhook._bot = bot

    try:
        httpd = HTTPServer((name, port), webhook)

        httpd.socket = ssl.wrap_socket(
          httpd.socket,
          certfile=certfile,
          server_side=True)

        sa = httpd.socket.getsockname()
        print(_("listener: api on {}, port {}...").format(sa[0], sa[1]))

        httpd.serve_forever()
    except IOError:
        # do not run sink without https!
        print(_("listener: api : pem file possibly missing or broken (== '{}')").format(certfile))
        httpd.socket.close()
    except OSError as e:
        # Could not connect to HTTPServer!
        print(_("listener: api : requested access could not be assigned. Is something else using that port? (== '{}:{}')").format(name, port))
    except KeyboardInterrupt:
        httpd.socket.close()

class webhookReceiver(BaseHTTPRequestHandler):
    _bot = None

    def _handle_incoming(self, path, query_string, payload):

        #path if needed for API
        #path = path.split("/")

        if "content" in payload and "sendto" in payload:
            self._scripts_command(payload["sendto"], payload["content"])

        else:
            print("Invalid payload: {}".format(payload))

        print(_("handler finished"))

    def _scripts_command(self, conv_or_user_id, content):
        try:
            # Create the fake ConversationEvent to pass the command through
            event = ConversationEvent()

            if conv_or_user_id.isdigit(): # Assuming user_id is always digit only
                # Private chat
                event.user_id = conv_or_user_id
                event.conv_id = webhookReceiver._bot.get_1to1(conv_or_user_id)
            else:
                # Potentially group chat. Pick first user found in group chat
                event.user_id = webhookReceiver._bot.get_users_in_conversation(conv_or_user_id)[0]
                event.conv_id = conv_or_user_id

            event.conv = webhookReceiver._bot._conv_list.get(event.conv_id)
            event.event_id = randrange(1, 9999999999, 1) # Create a random event_id
            event.user = event.conv.get_user(event.user_id)
            event.timestamp = time.time()
            event.text = content.strip()

            event.print_debug()

            webhookReceiver._bot._handlers.handle_command(event)
        except Exception as e:
            print(e)

    def do_POST(self):
        """
            receives post, handles it
        """
        print(_('receiving POST...'))
        data_string = self.rfile.read(int(self.headers['Content-Length'])).decode('UTF-8')
        self.send_response(200)
        message = bytes('OK', 'UTF-8')
        self.send_header("Content-type", "text")
        self.send_header("Content-length", str(len(message)))
        self.end_headers()
        self.wfile.write(message)
        print(_('connection closed'))

        # parse requested path + query string
        _parsed = urlparse(self.path)
        path = _parsed.path
        query_string = parse_qs(_parsed.query)

        print(_("incoming path: {}").format(path))

        # parse incoming data
        payload = json.loads(data_string)

        print(_("payload {}").format(payload))

        self._handle_incoming(path, query_string, payload)
