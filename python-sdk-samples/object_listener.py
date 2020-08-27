# !/usr/bin/env python3
from collections import defaultdict
from threading import Lock
import affvisionpy as af

class ObjectListener(af.ObjectListener):
    """
    ObjectListener class that return object metrics for processed frames.

    """

    def __init__(self, object_interval):
        super(ObjectListener, self).__init__()

        self.count = 0
        self.process_last_ts = 0.0
        self.object_interval = object_interval
        self.mutex = Lock()
        self.time_metrics_dict = defaultdict()
        self.objects = defaultdict()
        self.confidence = defaultdict()
        self.bounding_box = defaultdict()
        self.type = defaultdict()

    def results_updated(self, objects, frame):
        timestamp = frame.timestamp()

        self.mutex.acquire()
        # avoid div by 0 error on the first frame
        try:
            process_fps = 1000.0 / (frame.timestamp() - self.process_last_ts)
        except:
            process_fps = 0
        print("timestamp:" + str(round(timestamp, 0)), "Frame " + str(self.count),
              "pfps: " + str(round(process_fps, 0)))

        self.count += 1
        self.process_last_ts = frame.timestamp()
        self.objects = objects
        self.clear_all_dictionaries()
        for oid, obj in objects.items():
            bbox = obj.bounding_box
            self.bounding_box[oid] = [bbox.getTopLeft().x,
                                      bbox.getTopLeft().y,
                                      bbox.getBottomRight().x,
                                      bbox.getBottomRight().y]
            self.type[oid] = obj.type
            self.confidence[oid] = obj.confidence
        self.mutex.release()

    def get_callback_interval(self):
        callback = defaultdict()
        callback[af.Feature.phones] = self.object_interval
        return callback

    def clear_all_dictionaries(self):
        """
        Clears the dictionary values
        """
        self.confidence.clear()
        self.confidence = defaultdict()
        self.bounding_box.clear()
        self.bounding_box = defaultdict()
        self.type.clear()
        self.type = defaultdict()
