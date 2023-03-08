import unittest.main
from unittest.mock import Mock
from unittest.mock import patch
from unittest import TestCase

import json
import os
import pandas as pd
import sys

# mock all google cloud modules
sys.modules['google.cloud'] = Mock()

import main


PUBSUB_MOCK = Mock()

# mock environment variables
@patch.dict(os.environ, {"PROJECT_ID":'id', "WEIGHTS_DATABASE":'al_weights.csv'})
# replace access to weights file in cloud bucket with access to local file
@patch('pandas.read_csv', Mock(return_value=pd.read_csv("extractValue/totalWeight/al_weights.csv")))
@patch('main.PUB_CLIENT', PUBSUB_MOCK)
class TestWeightExtraction(TestCase):
    
    def setUp(self, *args):
        # default request contains valid fields
        self.request = Mock(json={"valueString":"1200.123", "topic":"t"})
        PUBSUB_MOCK = Mock()


    def test_successCase(self, *args):
        # tests the valid request set up as default for other tests
        main.extract_total_weight(self.request)
        message = json.loads(PUBSUB_MOCK.publish.call_args.args[1])

        self.assertTrue(message['success'])
        self.assertIsNone(message['error'])
        self.assertTrue(message["checks"]["decimalPlaceCheck"])
        self.assertTrue(message["checks"]["extremeValueCheck"])
        self.assertEqual(message["value"], "1200.123")


    def test_edgeCase_decimalPlaces(self, *args):
        testCases = [
            "0967.123", 
            "1345.550", 
            "1345.555"]
        
        for test in testCases:
            self.request.json["valueString"] = test
            with self.subTest(test_data=test):
                main.extract_total_weight(self.request)
                message = json.loads(PUBSUB_MOCK.publish.call_args.args[1])
                self.assertTrue(message["checks"]["decimalPlaceCheck"])


    def test_edgeCase_valueExtraction(self, *args):
        testCases = {
            "12345.534kgs":"12345.534",
            ": 12345.534":"12345.534",
            ": 12345.534kgs":"12345.534"}

        for test in testCases.keys():
            self.request.json["valueString"] = test
            with self.subTest(test_data=test):
                main.extract_total_weight(self.request)
                message = json.loads(PUBSUB_MOCK.publish.call_args.args[1])
                self.assertEqual(message["value"], testCases[test])


    def test_failureCase_noAppropriateValue(self, *args):
        testCases = [
            "weight",
            "total.weight"]
        
        for test in testCases:
            self.request.json["valueString"] = test
            with self.subTest(test_data=test):
                main.extract_total_weight(self.request)
                message = json.loads(PUBSUB_MOCK.publish.call_args.args[1])
                self.assertFalse(message['success'])
                self.assertEqual(message['error']['description'], "Matched field value does not contain number")


    def test_failureCase_extremeValue(self, *args):
        testCases = [
            "1.000",
            "50.000",
            "500000.000",
            "250000.000"]
        
        for test in testCases:
            self.request.json["valueString"] = test
            with self.subTest(test_data=test):
                main.extract_total_weight(self.request)
                message = json.loads(PUBSUB_MOCK.publish.call_args.args[1])
                self.assertFalse(message["checks"]["extremeValueCheck"])


    def test_failureCase_decimalPlaces(self, *args):
        testCases = [
            "01967.12", 
            "12345.00", 
            "12345.5555",
            "12345.0000"]
        
        for test in testCases:
            self.request.json["valueString"] = test
            with self.subTest(test_data=test):
                main.extract_total_weight(self.request)
                message = json.loads(PUBSUB_MOCK.publish.call_args.args[1])
                self.assertFalse(message["checks"]["decimalPlaceCheck"])


    def test_failureCase_malformedRequest(self, *args):
        testCases = [
            {"topic":"t"}, 
            {"valueString":"12345.123"}, 
            {"topic":None, "valueString":"12345.123"},
            {"topic":"t", "valueString":None}]
        
        for test in testCases:
            self.request.json = test
            with self.subTest(test_data=test):
                self.assertRaises(ValueError, main.extract_total_weight, self.request)


if __name__ == "__main__":
    unittest.main()