import os
import json
import pyqvrpro
import datetime
from flask import Flask, send_from_directory, request

def root_dir():  # pragma: no cover
    return os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__)

# User options are stored here when run as an addon
json_file_path = '/data/options.json'

# Open and read the JSON file
try:
    with open(json_file_path, 'r') as json_file:
        user_options = json.load(json_file)
        app.logger.info(user_options)
except FileNotFoundError:
    print(f"File not found: {json_file_path}")
except json.JSONDecodeError as e:
    print(f"JSON decoding error: {e}")

app.config['RECORDING_DIR'] = user_options.get("RECORDING_DIR") if user_options.get("RECORDING_DIR") is not None else os.path.join(root_dir(), 'recording')
app.config['QVRPRO_USER'] = user_options.get("QVRPRO_USER")
app.config['QVRPRO_PW'] = user_options.get("QVRPRO_PW")
app.config['QVRPRO_HOST'] = user_options.get("QVRPRO_HOST")
app.config['QVRPRO_PROTOCOL'] = user_options.get('QVRPRO_PROTOCOL')
app.config['QVRPRO_PORT'] = user_options.get('QVRPRO_PORT') if user_options.get("QVRPRO_PORT") is not None else 443
app.config['VERIFY_SSL'] = False if user_options.get("VERIFY_SSL") == 0 else True
app.config['CAMERA_GUID'] = user_options.get("CAMERA_GUID") if user_options.get("CAMERA_GUID") is not None else ''

def get_camera_guid(client):
    camera_guid = app.config.get("CAMERA_GUID")
    if camera_guid == '':
        app.logger.info("Getting new camera guid")
        cameras = client.list_cameras()
        if cameras and len(cameras["datas"]) > 0:
            camera_guid = cameras["datas"][0]["guid"]
            app.logger.info(f"camera__guid: {camera_guid}")
            app.config["CAMERA_GUID"] = str(camera_guid)
        else:
            app.logger.error(f"Camera guid not found cameras: {cameras}")

    return camera_guid

def get_now_timestamp():
    now = datetime.datetime.now()
    return int(now.timestamp() * 1000)

def get_offset_timestamp(offset):
    now = datetime.datetime.now()
    timestamp = now + datetime.timedelta(seconds=offset)
    return int(timestamp.timestamp() * 1000)

@app.route('/list_cameras', methods=["GET"])
def list_recording():
    client = pyqvrpro.Client(app.config['QVRPRO_USER'], app.config['QVRPRO_PW'], app.config['QVRPRO_HOST'], app.config['QVRPRO_PROTOCOL'], app.config['QVRPRO_PORT'], verify_SSL=app.config['VERIFY_SSL'])
    response = client.list_cameras()
    return response, 200, {'Content-Type': 'application/json'}

@app.route('/get_recording', methods=["GET"])
def get_recording():
    pre_period_param = request.args.get("pre_period", default="", type=int)
    post_period_param = request.args.get("post_period", default="", type=int)
    offset_param = request.args.get("offset", default="", type=int)
    pre_period = pre_period_param * 1000 if pre_period_param != "" else 10000
    post_period = post_period_param * 1000 if post_period_param != "" else 1000
    offset = offset_param if offset_param != "" else 0

    client = pyqvrpro.Client(app.config['QVRPRO_USER'], app.config['QVRPRO_PW'], app.config['QVRPRO_HOST'], app.config['QVRPRO_PROTOCOL'], app.config['QVRPRO_PORT'], verify_SSL=app.config['VERIFY_SSL'])
    camera_guid = get_camera_guid(client)

    if camera_guid == '':
        return {
            'error': 'Camera GUID not provided and unable to retrieve camera GUID'
        }, 404, {'Content-Type': 'application/json'}

    timestamp = get_offset_timestamp(offset)

    app.logger.info({
        'request_time': datetime.datetime.now().strftime("%Y-%m-%d_%H:%M:%S"),
        'timestamp': timestamp,
        'pre_period': pre_period,
        'post_period': post_period,
        'offset': offset
    })

    response = client.get_recording(timestamp=timestamp, camera_guid=camera_guid, channel_id=0, pre_period=pre_period, post_period=post_period)

    # If the response is a type application/json, it means error has occurred
    if response.headers['content-type'] == 'application/json':
        app.logger.error({
            'error_response': response.json(),
            'timestamp': timestamp,
            'pre_period': pre_period,
            'post_period': post_period,
            'offset': offset
        })
        return response.json(), 404, {'Content-Type': 'application/json'}

    if response.headers['content-type'] == 'video/mp4':
        return response.content, 200, {'Content-Type': 'video/mp4'}

    return "Invalid Response"

@app.route('/generate_qvr_recording', methods=["GET"])
def generate_qvr_recording():
    client = pyqvrpro.Client(app.config['QVRPRO_USER'], app.config['QVRPRO_PW'], app.config['QVRPRO_HOST'], app.config['QVRPRO_PROTOCOL'], app.config['QVRPRO_PORT'], verify_SSL=app.config['VERIFY_SSL'])
    camera_guid = get_camera_guid(client)

    timestamp_string = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    filename = f'{timestamp_string}.mp4'
    filepath = os.path.join(app.config['RECORDING_DIR'], filename)
    timestamp = get_now_timestamp()

    recording =  client.get_recording(timestamp=timestamp, camera_guid=camera_guid, channel_id=0 )

    recording_path = client.get_recording_path(recording, filepath)

    response = {'full_path': recording_path, 'filename': filename}
    return response, 200, {'Content-Type': 'application/json'}

@app.route('/get_recording/<path:filename>', methods=["GET"])
def get_recording_file(filename):
    return send_from_directory(app.config['RECORDING_DIR'], filename)

@app.route('/delete_recordings/<path:filename>', methods=["GET", "POST"])
def delete_recording(filename):
    app.logger.info(f"Trying to delete file: {os.path.join(app.config['RECORDING_DIR'], filename)}")
    if os.path.exists(os.path.join(app.config['RECORDING_DIR'], filename)):
        os.remove(os.path.join(app.config['RECORDING_DIR'], filename))
        app.logger.info(f"Deleted: {os.path.join(app.config['RECORDING_DIR'], filename)}")
        return "OK"
    else:
        app.logger.error("Error deleting file!")
        return "ERROR"

@app.route('/health_check', methods=["GET"])
def get_health_check():
    health_check_res = {"status": "healthy"}
    return health_check_res, 200, {'Content-Type': 'application/json'}

if __name__ == '__main__':
   app.run(debug = True)