import unittest.main
from unittest.mock import Mock
from unittest.mock import patch
from unittest import TestCase

import os
import sys
import json

GOOGLE_MOCK = Mock()
sys.modules['google.cloud'] = GOOGLE_MOCK
sys.modules['gcsfs'] = Mock()

import main

@patch.dict(os.environ, {
    "PROJECT_ID":"id",
    "PROCESSOR_ID":"id", 
    "OUTPUT_BUCKET":"output",
    "URL":"url",
    "LOCATION":"europe-west-2",
    "LOCATION_SHORT":"eu",
    "QUEUE":"q",
    "SAE":"servAcc"})
@patch("main.ClientOptions")
class TestImageProcessing(TestCase):

    def setUp(self, *args):
        
        # set up a way to read the HTTP message generated by the receiveImage routine
        self.return_message = {}
        def assignReturn(to_ret):
            self.return_message = to_ret
        GOOGLE_MOCK.tasks_v2beta3.HttpRequest.side_effect = \
            lambda url, oidc_token, headers, body: \
                assignReturn(json.loads(body))
        
        self.request = Mock(json={
            "bucket":"bucket",
            "name":"name",
            "fields":["fields"]})

        # patch up the call to documentParse AI, and the return values
        self.parseDocumentPatch = Mock()
        self.parseDocumentPatch.return_value = self.parseDocumentPatch
        self.parseDocumentPatch.pages = [Mock(return_value="page")]
        for page in self.parseDocumentPatch.pages:
            page.form_fields = [Mock(return_value="total weight")]
            for field in page.form_fields:
                field.field_name.text_anchor.content = Mock(return_value="total weight")
                field.field_value.text_anchor.content = Mock(return_value="12345.123")
                field.field_name.conficence = Mock(return_value=1)
                field.field_value.confidence = Mock(return_value=1)


    def test_successCase(self, *args):
        with patch('main.parse_document', self.parseDocumentPatch):
            st, num, l = main.process_image(self.request)
            self.assertEqual(st, "Ok")
            self.assertEqual(num, 204)
            self.assertEqual(self.return_message["bucket"], "output")
            self.assertEqual(self.return_message["name"],"name.csv")
            self.assertEqual(self.return_message["fields"], ["fields"])

    
    def test_failureCase_malformedRequest(self, *args):
        testCases = [
            {"bucket":"b", "name":"n"},
            {"bucket":"b", "fields":["field1"]},
            {"name":"n", "fields":["field1"]}]

        for test in testCases:
            self.request.json = test
            with self.subTest(test_data=test):
                st, num, l = main.process_image(self.request)
                self.assertEqual(num, 400)


if __name__ == "__main__":
    unittest.main()