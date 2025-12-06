import argparse
import asyncio
import json
import logging
import os
import random
import string
from aiohttp import web
from aiortc import RTCPeerConnection, RTCSessionDescription, MediaStreamTrack, MediaRelay

logging.basicConfig(level=logging.INFO)
ROOT = os.path.dirname(__file__)

# Global structures
rooms = {}  # room_id -> {"tracks": [MediaStreamTrack,...], "pcs": set()}
relay = MediaRelay()

# Utility: generate room id
def gen_room_id(n=6):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=n))

async def index(request):
    return web.FileResponse(os.path.join(ROOT, "static", "index.html"))

async def viewer_page(request):
    return web.FileResponse(os.path.join(ROOT, "static", "viewer.html"))

async def static_handler(request):
    path = request.match_info.get('filename')
    full = os.path.join(ROOT, "static", path)
    if os.path.exists(full):
        return web.FileResponse(full)
    raise web.HTTPNotFound()

# Endpoint: broadcaster posts an offer, server creates a room and stores relayed tracks
async def offer(request):
    params = await request.json()
    sdp = params["sdp"]
    type_ = params["type"]

    room_id = gen_room_id()
    pc = RTCPeerConnection()
    rooms[room_id] = {"tracks": [], "pcs": set([pc])}
    logging.info("Created room %s (pc id=%s)", room_id, id(pc))

    @pc.on("track")
    def on_track(track):
        logging.info("Track %s received for room %s kind=%s", track.id, room_id, track.kind)
        # Use relay to allow multiple subscribers
        relayed = relay.subscribe(track)
        rooms[room_id]["tracks"].append(relayed)

        @track.on("ended")
        async def on_ended():
            logging.info("Track %s ended", track.id)

    # set remote description (offer from browser)
    await pc.setRemoteDescription(RTCSessionDescription(sdp, type_))
    # create answer
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    # return sdp and room_id
    return web.json_response({"sdp": pc.localDescription.sdp, "type": pc.localDescription.type, "room": room_id})

# Endpoint: viewer posts offer, server adds relayed tracks to this peer and returns an answer
async def view_offer(request):
    room_id = request.match_info.get("room")
    if room_id not in rooms:
        raise web.HTTPNotFound(text="Room not found")

    params = await request.json()
    sdp = params["sdp"]
    type_ = params["type"]

    pc = RTCPeerConnection()
    rooms[room_id]["pcs"].add(pc)
    logging.info("Viewer connected to room %s (pc id=%s)", room_id, id(pc))

    # Add relayed tracks from room to this viewer pc
    for t in rooms[room_id]["tracks"]:
        try:
            pc.addTrack(t)
            logging.info("Added relayed track to viewer pc id=%s", id(pc))
        except Exception as e:
            logging.warning("Error adding track: %s", e)

    # set remote description (offer from viewer)
    await pc.setRemoteDescription(RTCSessionDescription(sdp, type_))
    # create answer for viewer
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    # When connection closes, remove from room
    async def on_connection_state_change():
        logging.info("Connection state (%s) for pc id=%s", pc.connectionState, id(pc))
        if pc.connectionState == "failed" or pc.connectionState == "closed":
            try:
                await pc.close()
            finally:
                rooms[room_id]["pcs"].discard(pc)

    pc.on("connectionstatechange", lambda: asyncio.ensure_future(on_connection_state_change()))

    return web.json_response({"sdp": pc.localDescription.sdp, "type": pc.localDescription.type})

# Cleanup route (optional) - close room and pcs
async def close_room(request):
    room_id = request.match_info.get("room")
    if room_id in rooms:
        for pc in list(rooms[room_id]["pcs"]):
            try:
                await pc.close()
            except Exception:
                pass
        del rooms[room_id]
    return web.Response(text="closed")

def main():
    parser = argparse.ArgumentParser(description="Simple screen-share server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", default=8080, type=int)
    args = parser.parse_args()

    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_get("/viewer.html", viewer_page)
    app.router.add_get("/static/{filename}", static_handler)
    app.router.add_post("/offer", offer)  # broadcaster posts offer -> create room
    app.router.add_post("/view/{room}/offer", view_offer)  # viewer posts offer for room
    app.router.add_post("/close/{room}", close_room)

    logging.info("Starting server on http://%s:%s", args.host, args.port)
    web.run_app(app, host=args.host, port=args.port)

if __name__ == "__main__":
    main()
