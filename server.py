from flask import Flask, send_from_directory, request, jsonify
import random, string, json

app = Flask(__name__, static_folder="static")

# In-memory rooms: { room_id: { "offer": sdp, "answers": [] } }
rooms = {}

def gen_id(n=6):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=n))

@app.route("/")
def index():
    return send_from_directory("static", "index.html")

@app.route("/viewer")
def viewer_page():
    return send_from_directory("static", "viewer.html")

@app.route("/create_room", methods=["POST"])
def create_room():
    data = request.json
    offer = data["offer"]
    room = gen_id()
    
    rooms[room] = {
        "offer": offer,
        "answers": []
    }
    
    return jsonify({"room": room})

@app.route("/get_offer/<room>")
def get_offer(room):
    if room not in rooms:
        return jsonify({"error": "Room not found"}), 404
    return jsonify({"offer": rooms[room]["offer"]})

@app.route("/submit_answer/<room>", methods=["POST"])
def submit_answer(room):
    if room not in rooms:
        return jsonify({"error": "Room not found"}), 404
    data = request.json
    answer = data["answer"]
    rooms[room]["answers"].append(answer)
    return jsonify({"status": "ok"})

@app.route("/get_answers/<room>")
def get_answers(room):
    if room not in rooms:
        return jsonify({"answers": []})
    return jsonify({"answers": rooms[room]["answers"]})

@app.route("/static/<path:path>")
def static_files(path):
    return send_from_directory("static", path)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)
