# !/usr/bin/env python3
import argparse
import sys
import os
import time
import csv
from collections import defaultdict

import affvisionpy as af
import cv2

from listener import Listener as ImageListener
from object_listener import ObjectListener as ObjectListener
from occupant_listener import OccupantListener as OccupantListener

from display_metrics import (draw_metrics, check_bounding_box_outside, draw_bounding_box, draw_affectiva_logo,
                             get_affectiva_logo, get_bounding_box_points, draw_objects, draw_occupants)

# Constants
NOT_A_NUMBER = 'nan'
DEFAULT_FRAME_WIDTH = 1920
DEFAULT_FRAME_HEIGHT = 1080
DEFAULT_FILE_NAME = "default"
DATA_DIR_ENV_VAR = "AFFECTIVA_VISION_DATA_DIR"
OBJECT_CALLBACK_INTERVAL = 500
OCCUPANT_CALLBACK_INTERVAL = 500

HEADER_ROW_FACES = ['TimeStamp', 'faceId', 'upperLeftX', 'upperLeftY', 'lowerRightX', 'lowerRightY', 'confidence',
                    'interocular_distance',
                    'pitch', 'yaw', 'roll', 'joy', 'anger', 'surprise', 'valence', 'fear', 'sadness', 'disgust',
                    'neutral', 'contempt', 'smile',
                    'brow_raise', 'brow_furrow', 'nose_wrinkle', 'upper_lip_raise', 'mouth_open', 'eye_closure',
                    'cheek_raise', 'yawn',
                    'blink', 'blink_rate', 'eye_widen', 'inner_brow_raise', 'lip_corner_depressor', 'gaze_region',
                    'gaze_confidence', 'glasses'
                    ]

HEADER_ROW_OBJECTS = ['TimeStamp', 'objectId', 'confidence', 'upperLeftX', 'upperLeftY', 'lowerRightX', 'lowerRightY',
                      'ObjectType']

HEADER_ROW_OCCUPANTS = ['TimeStamp', 'occupantId', 'confidence', 'regionId', 'regionType', 'upperLeftX', 'upperLeftY', 'lowerRightX', 'lowerRightY']

header_row = []

identity_names_dict = defaultdict()

def run(csv_data):
    """
    Starting point of the program, initializes the detector, processes a frame and then writes metrics to frame
 
        Parameters
        ----------
        csv_data: list
            Values to hold for each frame
    """
    parser, args = parse_command_line()
    input_file, data, max_num_of_faces, csv_file, output_file, frame_width, frame_height = get_command_line_parameters(
        parser, args)

    start_time = 0
    if isinstance(input_file, int):
        start_time = time.time()
        detector = af.FrameDetector(data, max_num_faces=max_num_of_faces)
    else:
        detector = af.SyncFrameDetector(data, max_num_of_faces)

    capture_file = cv2.VideoCapture(input_file)

    if not args.video:
        capture_file.set(cv2.CAP_PROP_FRAME_HEIGHT, frame_height)
        capture_file.set(cv2.CAP_PROP_FRAME_WIDTH, frame_width)
        # If cv2 silently fails, default to 1920 x 1080 instead of 640 x 480
        if capture_file.get(3) != frame_width or capture_file.get(4) != frame_height:
            print(frame_width, "x", frame_height, "is an unsupported resolution, defaulting to 1920 x 1080")
            capture_file.set(cv2.CAP_PROP_FRAME_HEIGHT, DEFAULT_FRAME_HEIGHT)
            capture_file.set(cv2.CAP_PROP_FRAME_WIDTH, DEFAULT_FRAME_WIDTH)
            frame_width = DEFAULT_FRAME_WIDTH
            frame_height = DEFAULT_FRAME_HEIGHT

        file_width = frame_width
        file_height = frame_height

    else:
        file_width = int(capture_file.get(3))
        file_height = int(capture_file.get(4))

    out = None
    if output_file is not None:
        out = cv2.VideoWriter(output_file, cv2.VideoWriter_fourcc('M', 'J', 'P', 'G'), 10, (file_width, file_height))

    logo = get_affectiva_logo(file_width, file_height)

    if args.show_face:
        process_face_input(detector, args, capture_file, input_file, start_time, output_file, out, logo)
    elif args.show_object:
        process_object_input(detector, capture_file, input_file, start_time, output_file, out, logo)
    elif args.show_occupant:
        process_occupant_input(detector, capture_file, input_file, start_time, output_file, out, logo)


    capture_file.release()
    cv2.destroyAllWindows()
    detector.stop()

    # If video file is provided as an input
    if not isinstance(input_file, int):
        if csv_file == DEFAULT_FILE_NAME:
            if os.sep in input_file:
                csv_file = str(input_file.rsplit(os.sep, 1)[1])
            csv_file = csv_file.split(".")[0]
        write_csv_data_to_file(csv_data, csv_file)
    else:
        if not csv_file == DEFAULT_FILE_NAME:
            write_csv_data_to_file(csv_data, csv_file)

def process_face_input(detector, args, capture_file, input_file, start_time, output_file, out, logo):
    count = 0
    curr_timestamp = 0
    last_timestamp = 0

    features = {af.Feature.expressions, af.Feature.emotions, af.Feature.gaze, af.Feature.appearances}
    if args.show_identity:
        features.add(af.Feature.identity)

    detector.enable_features(features)

    listener = ImageListener()
    detector.set_image_listener(listener)

    detector.start()

    while capture_file.isOpened():
        # Capture frame-by-frame
        ret, frame = capture_file.read()

        if ret == True:

            height = frame.shape[0]
            width = frame.shape[1]
            if isinstance(input_file, int):
                curr_timestamp = (time.time() - start_time) * 1000.0
            else:
                curr_timestamp = int(capture_file.get(cv2.CAP_PROP_POS_MSEC))
            if curr_timestamp > last_timestamp or count == 0: # if there's a problem with the timestamp, don't process the frame
             
                last_timestamp = curr_timestamp
                afframe = af.Frame(width, height, frame, af.ColorFormat.bgr, int(curr_timestamp))
                count += 1

                try:
                    detector.process(afframe)

                except Exception as exp:
                    print(exp)

                listener.mutex.acquire()
                faces = listener.faces
                measurements_dict = listener.measurements_dict.copy()
                expressions_dict = listener.expressions_dict.copy()
                emotions_dict = listener.emotions_dict.copy()
                bounding_box_dict = listener.bounding_box_dict.copy()
                gaze_metric_dict = listener.gaze_metric_dict.copy()
                glasses_dict = listener.glasses_dict.copy()
                if args.show_identity:
                    identities_dict = listener.identities_dict.copy()

                listener.mutex.release()

                listener_metrics = {
                    "measurements": measurements_dict,
                    "expressions": expressions_dict,
                    "emotions": emotions_dict,
                    "bounding_box": bounding_box_dict,
                    "gaze_metric": gaze_metric_dict,
                    "glasses": glasses_dict
                }
                if args.show_identity:
                    listener_metrics["identities"] = identities_dict

                write_face_metrics_to_csv_data_list(csv_data, round(curr_timestamp, 0), listener_metrics)


                draw_affectiva_logo(frame, logo, width, height)
                if len(faces) > 0 and not check_bounding_box_outside(width, height, bounding_box_dict):
                    draw_bounding_box(frame, listener_metrics)
                    draw_metrics(frame, listener_metrics, identity_names_dict)

                cv2.imshow('Processed Frame', frame)

                if output_file is not None:
                    out.write(frame)

                if cv2.waitKey(1) == 27:
                    break
            else:
                print("skipped a frame due to the timestamp not incrementing - old timestamp %f, current timestamp %f" % 
                        (last_timestamp,curr_timestamp))
        else:
            break

def process_object_input(detector, capture_file, input_file, start_time, output_file, out, logo):
    count = 0
    last_timestamp = 0

    # only enabling phones for now, TODO: add child seat later
    detector.enable_feature(af.Feature.phones)

    # callback interval
    listener = ObjectListener(OBJECT_CALLBACK_INTERVAL)
    detector.set_object_listener(listener)

    detector.start()

    print("Setting up object detection")

    while capture_file.isOpened():
        # Capture frame-by-frame
        ret, frame = capture_file.read()

        if ret:

            height = frame.shape[0]
            width = frame.shape[1]
            if isinstance(input_file, int):
                curr_timestamp = (time.time() - start_time) * 1000.0
            else:
                curr_timestamp = int(capture_file.get(cv2.CAP_PROP_POS_MSEC))

            # if there's a problem with the curr_timestamp, don't process the frame
            if curr_timestamp > last_timestamp or count == 0:
                last_timestamp = curr_timestamp
                listener.time_metrics_dict['timestamp'] = curr_timestamp
                afframe = af.Frame(width, height, frame, af.ColorFormat.bgr, int(curr_timestamp))
                count += 1

                try:
                    detector.process(afframe)

                except Exception as exp:
                    print(exp)

                listener.mutex.acquire()
                objects = listener.objects
                bounding_box_dict = listener.bounding_box.copy()
                confidence_dict = listener.confidence.copy()
                type_dict = listener.type.copy()
                listener.mutex.release()

                listener_metrics = {
                    "bounding_box": bounding_box_dict,
                    "confidence": confidence_dict,
                    "object_type": type_dict
                }

                write_object_metrics_to_csv_data_list(csv_data, round(curr_timestamp, 0), listener_metrics)
                if len(objects) > 0 and not check_bounding_box_outside(width, height, listener_metrics["bounding_box"]):
                    draw_objects(frame, listener_metrics)

                draw_affectiva_logo(frame, logo, width, height)
                cv2.imshow('Processed Frame', frame)
                if output_file is not None:
                    out.write(frame)

                if cv2.waitKey(1) == 27:
                    break
            else:
                print("skipped a frame due to the timestamp not incrementing - old timestamp %f, new timestamp %f" % (
                    last_timestamp, curr_timestamp))
        else:
            break


def process_occupant_input(detector, capture_file, input_file, start_time, output_file, out, logo):
    count = 0
    last_timestamp = 0

    detector.enable_features({af.Feature.faces, af.Feature.bodies, af.Feature.occupants})

    # callback interval
    listener = OccupantListener(OCCUPANT_CALLBACK_INTERVAL)
    detector.set_occupant_listener(listener)

    detector.start()
    print("Setting up occupant detection")

    while capture_file.isOpened():
        # Capture frame-by-frame
        ret, frame = capture_file.read()

        if ret:
            height = frame.shape[0]
            width = frame.shape[1]
            if isinstance(input_file, int):
                curr_timestamp = (time.time() - start_time) * 1000.0
            else:
                curr_timestamp = int(capture_file.get(cv2.CAP_PROP_POS_MSEC))

            # if there's a problem with the curr_timestamp, don't process the frame
            if curr_timestamp > last_timestamp or count == 0:
                last_timestamp = curr_timestamp
                listener.time_metrics_dict['timestamp'] = curr_timestamp
                afframe = af.Frame(width, height, frame, af.ColorFormat.bgr, int(curr_timestamp))
                count += 1

                try:
                    detector.process(afframe)

                except Exception as exp:
                    print(exp)

                listener.mutex.acquire()
                occupants = listener.occupants
                bounding_box_dict = listener.bounding_box.copy()
                confidence_dict = listener.confidence.copy()
                region_id_dict = listener.regionId.copy()
                region_dict = listener.region.copy()
                region_type_dict = listener.regionType.copy()
                listener.mutex.release()

                listener_metrics = {
                    "bounding_box": bounding_box_dict,
                    "confidence": confidence_dict,
                    "region_id": region_id_dict,
                    "region": region_dict,
                    "region_type": region_type_dict,
                }

                write_occupant_metrics_to_csv_data_list(csv_data, round(curr_timestamp, 0), listener_metrics)
                if len(occupants) > 0 and not check_bounding_box_outside(width, height, listener_metrics["bounding_box"]):
                    draw_occupants(frame, listener_metrics)

                draw_affectiva_logo(frame, logo, width, height)
                cv2.imshow('Processed Frame', frame)
                if output_file is not None:
                    out.write(frame)

                if cv2.waitKey(1) == 27:
                    break
            else:
                print("skipped a frame due to the timestamp not incrementing - old timestamp %f, new timestamp %f" % (
                    last_timestamp, curr_timestamp))
        else:
            break

def write_face_metrics_to_csv_data_list(csv_data, timestamp, listener_metrics):
    """
    Write metrics per frame to a list
 
        Parameters
        ----------
        csv_data:
          list of per frame values to write to
        timestamp: int
           timestamp of each frame
        listener_metrics: dict
            dictionary of dictionaries, gives current listener state
 
    """
    global header_row
    if not listener_metrics["measurements"].keys():
        current_frame_data = {}
        current_frame_data["TimeStamp"] = timestamp
        for field in header_row[1:]:
            current_frame_data[field] = NOT_A_NUMBER
        csv_data.append(current_frame_data)
    else:
        for fid in listener_metrics["measurements"].keys():
            current_frame_data = {}
            current_frame_data["TimeStamp"] = timestamp
            current_frame_data["faceId"] = fid
            upperLeftX, upperLeftY, lowerRightX, lowerRightY = get_bounding_box_points(fid, listener_metrics["bounding_box"])
            current_frame_data["upperLeftX"] = upperLeftX
            current_frame_data["upperLeftY"] = upperLeftY
            current_frame_data["lowerRightX"] = lowerRightX
            current_frame_data["lowerRightY"] = lowerRightY
            for key, val in listener_metrics["measurements"][fid].items():
                current_frame_data[key.name] = round(val, 4)
            for key, val in listener_metrics["emotions"][fid].items():
                current_frame_data[key.name] = round(val, 4)
            for key, val in listener_metrics["expressions"][fid].items():
                current_frame_data[key.name] = round(val, 4)
            current_frame_data["confidence"] = round(listener_metrics["bounding_box"][fid][4], 4)

            if "identities" in listener_metrics:
                identity = listener_metrics["identities"][fid]
                current_frame_data["identity"] = identity
                if str(identity) in identity_names_dict:
                    current_frame_data["name"] = identity_names_dict[str(identity)]
                else:
                    current_frame_data["name"] = "Unknown"

            current_frame_data["gaze_region"] = listener_metrics["gaze_metric"][fid].gaze_region.name
            current_frame_data["gaze_confidence"] = str(listener_metrics["gaze_metric"][fid].confidence)
            current_frame_data["glasses"] = round(listener_metrics["glasses"][fid])
            csv_data.append(current_frame_data)

def write_object_metrics_to_csv_data_list(csv_data, timestamp, listener_metrics):
    """
    Write metrics per frame to a list

        Parameters
        ----------
        csv_data:
          list of per frame values to write to
        timestamp: int
           timestamp of each frame
        listener_metrics: dict
            dictionary of dictionaries, gives current listener state

    """
    global header_row
    current_frame_data = {}
    if "object_type" in listener_metrics:
        for oid in listener_metrics["object_type"].keys():
            current_frame_data["TimeStamp"] = timestamp
            current_frame_data["objectId"] = oid
            upperLeftX, upperLeftY, lowerRightX, lowerRightY = get_bounding_box_points(oid,
                                                                                       listener_metrics["bounding_box"])
            current_frame_data["upperLeftX"] = upperLeftX
            current_frame_data["upperLeftY"] = upperLeftY
            current_frame_data["lowerRightX"] = lowerRightX
            current_frame_data["lowerRightY"] = lowerRightY

            current_frame_data["confidence"] = round(listener_metrics["confidence"][oid])
            current_frame_data["ObjectType"] = listener_metrics["object_type"][oid].name
            csv_data.append(current_frame_data)
    else:
        current_frame_data["TimeStamp"] = timestamp
        for field in header_row[1:]:
            current_frame_data[field] = NOT_A_NUMBER
        csv_data.append(current_frame_data)

def write_occupant_metrics_to_csv_data_list(csv_data, timestamp, listener_metrics):
    """
    Write metrics per frame to a list

        Parameters
        ----------
        csv_data:
          list of per frame values to write to
        timestamp: int
           timestamp of each frame
        listener_metrics: dict
            dictionary of dictionaries, gives current listener state

    """
    global header_row
    current_frame_data = {}
    if "bounding_box" in listener_metrics:
        for occid in listener_metrics["bounding_box"].keys():
            current_frame_data["TimeStamp"] = timestamp
            current_frame_data["occupantId"] = occid
            upperLeftX, upperLeftY, lowerRightX, lowerRightY = get_bounding_box_points(occid,
                                                                                       listener_metrics["bounding_box"])
            current_frame_data["upperLeftX"] = upperLeftX
            current_frame_data["upperLeftY"] = upperLeftY
            current_frame_data["lowerRightX"] = lowerRightX
            current_frame_data["lowerRightY"] = lowerRightY

            current_frame_data["confidence"] = round(listener_metrics["confidence"][occid])
            current_frame_data["regionId"] = listener_metrics["region_id"][occid]
            current_frame_data["regionType"] = listener_metrics["region_type"][occid]
            csv_data.append(current_frame_data)
    else:
        current_frame_data["TimeStamp"] = timestamp
        for field in header_row[1:]:
            current_frame_data[field] = NOT_A_NUMBER
        csv_data.append(current_frame_data)

def write_csv_data_to_file(csv_data, csv_file):
    """
    Place logo on the screen
 
        Parameters
        ----------
        csv_data: list
           list to write the data from
        csv_file: list
           file to be written to
    """
    global header_row
    if ".csv" not in csv_file:
        csv_file = csv_file + ".csv"
    with open(csv_file, 'w') as c_file:
        writer = csv.DictWriter(c_file, fieldnames=header_row)
        writer.writeheader()
        for row in csv_data:
            writer.writerow(row)

    c_file.close()

def parse_command_line():
    """
    Make the options for command line
 
    Returns
    -------
    args: argparse object of the command line
    """
    parser = argparse.ArgumentParser(description="Sample code for demoing affvisionpy module on webcam or a saved video file.\n \
        By default, the program will run with the camera parameter displaying frames of size 1920 x 1080.\n")
    parser.add_argument("-d", "--data", dest="data", required=False, help="path to directory containing the models. \
                        Alternatively, specify the path via the environment variable " + DATA_DIR_ENV_VAR + "=/path/to/data/")
    parser.add_argument("-i", "--input", dest="video", required=False,
                        help="path to input video file")
    parser.add_argument("-n", "--num_faces", dest="num_faces", required=False, default=5,
                        help="number of faces to identify in the frame")
    parser.add_argument("-c", "--camera", dest="camera", required=False, const="0", nargs='?', default=0,
                        help="enable this parameter take input from the webcam and provide a camera id for the webcam")
    parser.add_argument("-o", "--output", dest="output", required=False,
                        help="name of the output video file")
    parser.add_argument("-f", "--file", dest="file", required=False, default=DEFAULT_FILE_NAME,
                        help="name of the output CSV file")
    parser.add_argument("-r", "--resolution", dest='res', metavar=('width', 'height'), nargs=2, default=[1920, 1080],
                        help="resolution in pixels (2-values): width height")
    parser.add_argument("--identity", dest="show_identity", action='store_true', help="show face with identity metrics")
    parser.add_argument("--object", dest="show_object", action='store_true', help="Enable object detection")
    parser.add_argument("--occupant", dest="show_occupant", action='store_true', help="Enable face detection")
    args = parser.parse_args()
    return parser, args

def read_identities_csv(data_dir):
    """Read the identities.csv file and return its contents (minus the header row) as a dict

    Parameters
    ----------
    data_dir: data directory path
    """
    lines = {}
    csv_path = data_dir + '/attribs/identities.csv'
    if os.path.isfile(csv_path):
        with open(csv_path, 'r') as file:
            reader = csv.reader(file)
            next(reader, None)  # skip header row
            for row in reader:
                lines[row[0]] = row[1]
    return lines

def get_command_line_parameters(parser, args):
    """
    read parameters entered on the command line.
 
        Parameters
        ----------
        args: argparse
            object of argparse module
 
        Returns
        -------
        tuple of str values
            details about input file name, data directory, num of faces to detect, output file name
    """
    if not args.video is None:
        input_file = args.video
        if not os.path.isfile(input_file):
            raise ValueError("Please provide a valid input video file")
    else:
        if str(args.camera).isdigit():
            input_file = int(args.camera)
        else:
            raise ValueError("Please provide an integer value for camera")

    data = args.data
    if not data:
        data = os.environ.get(DATA_DIR_ENV_VAR)
        if data == None:
            print("ERROR: Data directory not specified via command line or env var:", DATA_DIR_ENV_VAR, "\n")
            parser.print_help()
            sys.exit(1)
        print("Using value", data, "from env var", DATA_DIR_ENV_VAR)
    if not os.path.isdir(data):
        print("ERROR: Please check your data directory path\n")
        parser.print_help()
        sys.exit(1)

    args.show_face = False
    # minimum feature check
    if not (args.show_object or args.show_occupant):
        print("Setting up face detection by default")
        args.show_face = True
    # check for enabled feature request
    elif args.show_identity and args.show_object and args.show_occupant:
        print("ERROR: Can't enable all features at same time\n")
        parser.print_help()
        sys.exit(1)
    elif args.show_identity and args.show_object:
        print("ERROR: Can't enable identity with objects\n")
        parser.print_help()
        sys.exit(1)
    elif args.show_identity and args.show_occupant:
        print("ERROR: Can't enable identity with occupants\n")
        parser.print_help()
        sys.exit(1)
    elif args.show_object and args.show_occupant:
        print("ERROR: Can't enable objects with occupants\n")
        parser.print_help()
        sys.exit(1)



    global header_row
    if args.show_face:
        header_row = HEADER_ROW_FACES
        if args.show_identity:
            global identity_names_dict
            # read in the csv file that maps identities to names
            identity_names_dict = read_identities_csv(data)
            header_row.extend(['identity', 'name'])
    elif args.show_object:
        header_row = HEADER_ROW_OBJECTS
    elif args.show_occupant:
        header_row = HEADER_ROW_OCCUPANTS

    max_num_of_faces = int(args.num_faces)
    output_file = args.output
    csv_file = args.file
    frame_width = int(args.res[0])
    frame_height = int(args.res[1])
    return input_file, data, max_num_of_faces, csv_file, output_file, frame_width, frame_height


if __name__ == "__main__":
    csv_data = list()
    run(csv_data)