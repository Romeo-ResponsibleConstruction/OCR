# Data Analysis

To estimate $\lambda_1, \lambda_2, \lambda_3$ (see processExtractedData), we performed maximum likelihood estimation on manually labelled outputs of the OCR model, according to the following steps
1. If it is a legitimate field value, then note the true field name, `trueFieldName`. Omit any punctuation, like the colon in "Field Name:", since the formatting may be inconsistent.
2. If it is not, leave `trueFieldName` blank.
3. If there are `fieldValue` contains multiple field values corresponding to multiple legitimate field names, arbitrarily pick one.
4. If one field value is broken up across multiple identified `fieldValue`s, pick the `fieldValue` with the closest `fieldName` match to the true field name. Leave the rest blank.