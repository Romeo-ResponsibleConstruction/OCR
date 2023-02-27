# Database Upload
`[fileName].json` contains:
2. `extractedFields: list of String`
3. `fieldName`. Information associated with the extracted fieldName:
   1. `success: boolean`
   2. `value: Option of String` (the extracted value)
   3. `error: Option of {type: String, description: String}`
   4. `checks: Option of {check1: boolean, check2: boolean, ...}`

Where `value` and `checks` are non-`null` if and only if `success` is true, and `error` is non -`null` if and only if `success` is false. 