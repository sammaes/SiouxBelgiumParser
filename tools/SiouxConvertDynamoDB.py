#!/usr/bin/python

import os
import ConfigParser
import boto3
import botocore
from boto3.dynamodb.conditions import Key, Attr

dynamodb = boto3.resource('dynamodb', region_name='us-west-2', endpoint_url="http://localhost:8000")
dynamodb_client = boto3.client('dynamodb', region_name='us-west-2')


def delete_table(table_name):
    try:
        table = dynamodb.Table(table_name)
        table.delete()
    except:
        print 'Could not delete table %s' % table_name
        exit(1)


class SiouxConvertDynamoDB:
    # Config file
    _CONFIG_FILE = 'config.ini'

    def __init__(self):
        self._conf = ConfigParser.ConfigParser()
        config_file = os.path.join(os.getcwd(), self._CONFIG_FILE)

        if os.path.isfile(config_file):
            self._conf.read(config_file)
        else:
            raise RuntimeError("Could not locate config file '%s'." % config_file)

        self.config = {
            'URLS': ['IIS_DOMAIN', 'BASE_INTRA', 'BASE', 'EVENTS_OVERVIEW_EXT', 'BDAY_EXT'],
            'EVENTS': ['SOCIAL_PARTNER', 'SOCIAL_COLLEAGUE', 'POWWOW', 'TRAINING', 'EXP_GROUP', 'PRESENTATION'],
            'PARSE_EV': ['ELEMENT_EV', 'ARG_EV', 'VALUE_DATE_EV', 'VALUE_TITLE_EV', 'VALUE_LOCATION_EV', 'VALUE_CATEGORY_EV'],
            'PARSE_BDAY': ['ELEMENT_BDAY', 'ARG_BDAY', 'VALUE_SEPARATE_BDAY', 'VALUE_OVERALL_BDAY', 'TITLE_TODAY_BDAY', 'TITLE_FUTURE_BDAY', 'TITLE_PAST_BDAY', 'ROLE_COLLEGUE_BDAY', 'ROLE_COLLEGUE_CHILD', 'ROLE_COLLEGUE_PARTNER'],
            'P_D': ['TAB', 'TAB_ARG', 'TAB_VALUE', 'REC_ELEMENT', 'REC_ARG', 'REC_VALUE', 'DATE_ELEMENT', 'DATE_ARG', 'DATE_VALUE']
        }

        self._init_tables()

    def _init_tables(self):
        print "Deleting all tables..."
        delete_table('SIOUX_URLS')
        delete_table('SIOUX_EVENTS')
        delete_table('SIOUX_PARSE_EV')
        delete_table('SIOUX_PARSE_BDAY')
        delete_table('SIOUX_P_D')

        self.tables = {
            'URLS':       None,
            'EVENTS':     None,
            'PARSE_EV':   None,
            'PARSE_BDAY': None,
            'P_D':        None
        }

        print "Creating tables..."
        self.create_tables()

    def _get_config(self, key, value):
        """
        Get configuration value from config file.\n

        :param key:   Key found in configuration value. (string)\n
        :param value: Value associated with said key. (string)\n
        :return: Configuration value. (string)\n
        """
        return self._conf.get(key, value)

    def get_config_db(self, key, value):
        try:
            response = self.tables[key].query(KeyConditionExpression=Key('key').eq(value))
        except botocore.exceptions.ClientError as e:
            print(e.response['Error']['Message'])
        else:
            if len(response['Items']) != 1:
                print 'Unexpected response: %s' % response
                exit(1)
            return response['Items'][0]['value']

    def create_tables(self):
        for key, _ in self.config.items():
            try:
                self.tables[key] = dynamodb.create_table(
                    TableName='SIOUX_' + key,
                    KeySchema=[{'AttributeName': 'key', 'KeyType': 'HASH'},  # Partition key
                                {'AttributeName': 'value', 'KeyType': 'RANGE'}],  # Sort key
                    AttributeDefinitions=[ {'AttributeName': 'key', 'AttributeType': 'S'},
                                           {'AttributeName': 'value','AttributeType': 'S'}],
                    ProvisionedThroughput={'ReadCapacityUnits': 10, 'WriteCapacityUnits': 10}
                )
            except dynamodb_client.exceptions.ResourceInUseException:
                print 'Could not create table %s' % 'SIOUX' + key
                exit(1)

    def convert(self):
        for k_t, v_t in self.tables.items():
            for config in self.config[k_t]:
                response = v_t.put_item(Item={'key': config, 'value': self._get_config(k_t, config)})
                if response['ResponseMetadata']['HTTPStatusCode'] != 200:
                    print 'Could not add entry: %s -> %s (%s)' % (config, self._get_config(k_t, config), response)
                    exit(1)

    def scan_all_tables(self):
        print 'Result:\n'

        for k_t, v_t in self.tables.items():
            print 'Table: SIOUX_' + k_t
            response = v_t.scan()
            if response['ResponseMetadata']['HTTPStatusCode'] != 200:
                print 'Could not scan table: %s' % 'SIOUX_' + k_t
                exit(1)
            for i in response['Items']:
                print '  Key:%s Value:%s' % (i['key'], i['value'])
            print '\n'

# Main program:
if __name__ == "__main__":
    mover = SiouxConvertDynamoDB()

    print "Add config values to DynamoDB..."
    mover.convert()

    # print "Printing whole database..."
    # mover.scan_all_tables()
