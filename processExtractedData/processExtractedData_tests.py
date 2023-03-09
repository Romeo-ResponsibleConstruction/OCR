import unittest.main
from unittest.mock import Mock
from unittest.mock import patch
from unittest import TestCase

import os
import sys
import pandas as pd
import json

sys.modules['google.cloud'] = Mock()
import main

INPUTFILE_MOCK = Mock()

# need to make mock for SUB_CLIENT compatible with 'with'
class SubMock(Mock):
    def __enter__(self, *args):
        pass
    def __exit__(self, *args):
        pass

SUBCLIENT_MOCK = SubMock()
STOCLIENT_MOCK = Mock()

@patch.dict(os.environ, {
            "PROJECT_ID":"id",
            "OUTPUT_BUCKET":"b",
            "LOCATION":"europe-west2",
            "QUEUE":"q",
            "SAE":"servAcc",
            "TIMEOUT":"20",
            "REP_LAMBDA":"0.60458837",
            "DEL_LAMBDA":"0.63088535",
            "INS_LAMBDA":"0.81489784",
            "THRESHOLD_FIELD_LIKELIHOOD":"0.1",
            "THRESHOLD_POSTERIOR_FIELD_LIKELIHOOD":"0.7"})
@patch('pandas.read_csv', INPUTFILE_MOCK)
@patch('main.SUB_CLIENT', SUBCLIENT_MOCK)
@patch('main.STORAGE_CLIENT', STOCLIENT_MOCK)
@patch('main.enqueue_value_extraction')
class TestExtractedDataProcessing(TestCase):

    def setUp(self, *args):
        self.request = Mock(json={
            "bucket":"b",
            "name":"file",
            "fields":{"total weight":"totalWeight"}
        })

        # set default inputfile mock for OCR-returned data
        INPUTFILE_MOCK.return_value = pd.read_csv("processExtractedData/sample_input.csv")

        # set up access to returned data
        self.message = {}
        def assignReturn(to_ret):
            self.message = to_ret
        STOCLIENT_MOCK.get_bucket.return_value = STOCLIENT_MOCK
        STOCLIENT_MOCK.blob.return_value = STOCLIENT_MOCK
        STOCLIENT_MOCK.upload_from_string.side_effect = lambda x: assignReturn(json.loads(x))


    def test_successCase(self, *args):
        main.process_extracted_data(self.request)
        self.assertEqual(self.message["extractedFields"], ["total weight"])
        self.assertEqual(self.message["total weight"], {})


    def test_failureCase_lowFieldLikelihood(self, *args):
        with patch('numpy.max', return_value=0.001):
            main.process_extracted_data(self.request)
            self.assertFalse(self.message["total weight"]["success"])
            errormessage = self.message["total weight"]["error"]
            self.assertEqual(errormessage["type"], "field name")
            self.assertEqual(errormessage["description"], "No extracted field name with sufficiently high likelihood. Threshold: 0.1. Actual: 0.001")


    def test_failureCase_lowPosteriorLikelihood(self, *args):
        with patch("numpy.max", return_value=0.2):
            with patch('numpy.sum', return_value=1):
                main.process_extracted_data(self.request)
                self.assertFalse(self.message["total weight"]["success"])
                errormessage = self.message["total weight"]["error"]
                self.assertEqual(errormessage["type"], "field name")
                self.assertEqual(errormessage["description"], "Maximum a posteriori field name does not meet likelihood threshold. Threshold: 0.7. Actual: 0.2")


    def test_failureCase_malformedRequest(self, *args):
        testCases = [
            {"bucket":"b", "name":"n"},
            {"bucket":"b", "fields":{"total weight": "totalWeight"}},
            {"name":"n", "fields":{"total weight": "totalWeight"}}]

        for test in testCases:
            self.request.json = test
            with self.subTest(test_data=test):
                self.assertRaises(ValueError, main.process_extracted_data, self.request)


if __name__ == "__main__":
    unittest.main()