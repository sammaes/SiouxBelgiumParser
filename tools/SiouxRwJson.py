import os.path
import json
import sys
import datetime
sys.path.append(os.path.join(os.path.dirname(os.path.realpath(__file__)), os.pardir))

from SiouxParser import SiouxParser
from SiouxParser import ConfigInput
from SiouxParser import DataInput


class SiouxDataJson:
    def __init__(self):
        pass

    @staticmethod
    def read_json(events, birthdays):
        return_values = []

        if events:
            print 'Reading events from json...'
            with open('sioux_events.json', 'r') as fp:
                ev = json.load(fp)
                return_values.append(ev)

        if birthdays:
            print 'Reading birthdays from json...'
            with open('sioux_birthdays.json', 'r') as fp:
                bdays = json.load(fp)
                return_values.append(bdays)

        return return_values

    @staticmethod
    def write_json(events=None, birthdays=None):
        def default(o):
            if type(o) is datetime.date or type(o) is datetime.datetime:
                return o.isoformat()

        if events is not None:
            print 'Writing events to json...'
            with open('sioux_events.json', 'w') as fp:
                json.dump(events, fp, indent=4, default=default)

        if birthdays is not None:
            print 'Writing birthdays to json...'
            with open('sioux_birthdays.json', 'w') as fp:
                json.dump(birthdays, fp, indent=4, default=default)

# Main program:
if __name__ == "__main__":
    if len(sys.argv) == 1:
        print 'Please specify read/write'
        exit(1)

    sioux_json = SiouxDataJson()
    if str(sys.argv[1]).lower() == 'read':
        ret = sioux_json.read_json(True, True)

        import pdb
        pdb.set_trace()

    elif str(sys.argv[1]).lower() == 'write':
        parser = SiouxParser(config_input=ConfigInput.netrc, data_input=DataInput.https)

        print 'Retrieve events...'
        parser._get_events_https()

        print 'Retrieve birthdays...'
        parser._get_recent_birthdays_https()

        sioux_json.write_json(parser._RAW_EVENTS, parser._RAW_BDAYS)
