# Data Extraction and Validation

## 1. Data Extraction
**Packages**: `documentParse`

**Pre-condition**: `[fileName].jpg` or `[fileName].png` or `[fileName].jpeg` in `gpr_images` bucket

**Post-condition**: `[fileName].csv` in `gpr_raw_data` bucket. `[fileName].csv` contains `Field Name`,
`Field Name Confidence` (likelihood), `Field Value` and `Field Value Confidence` columns.

**Description**\
The `documentParse` code expects an image to be uploaded in the `gpr_images` bucket.
The image can be in a `png`, `jpg` or  `jpeg` format.
It then calls Google Cloud Platform's document parse OCR processor, extracts the `field name` and 
`field value` pairs, as well as their corresponding likelihoods, and populates a `csv` file with these values.

## 2. Data Validation
**Packages**: `dataAnalysis`, `postProcessing`

**Pre-condition**: `[fileName].csv` in `gpr_raw_data` bucket. `[fileName].csv` contains `Field Name`,
`Field Name Confidence` (likelihood), `Field Value` and `Field Value Confidence` columns.

**Post-condition**: `[fileName].json` in `gpr_sanitised_data` bucket. 

If data extraction and validation are successful, `[fileName].json` contains:
1. `success = true`, 
2. `fieldValue` (the extracted value), 
3. `checks` (set to true if passed, or false if failed)
   1. `extremeValueCheck`. Determines if the extracted value is an outlier (defined to be smaller or greater than 95% of weights)
   2. `decimalPlaceCheck`. Determines if the extracted value has 3 decimal places.

Otherwise, `[fileName].json` contains:
1. `success = false`
2. `description`, a description of why the extraction/validation failed. Possible reasons include:
   1. Maximum likelihood field name before normalisation was below threshold probability (document does not contain field name)
   2. Maximum likelihood field name after normalisation was below threshold probability (document contains multiple matching field names)
   3. Extracted value could not be parsed to a valid floating point number
   4. Extracted value parsed to a negative floating point number
3. `likelihoods`. If the threshold likelihoods were not met, the likelihood of the maximum a posteriori value. 

### 2.1 Probability Model
Consider the Levenshtein Distance $L$, which is computed as the minimum number of insertions $I$, deletions $D$ and replacements $R$ needed to 
convert one string $s_1$ into another string $s_2$

Now consider an arbitrary character $x$. We model *noise* introduced by the OCR system as insertions, deletions, or replacements, since the 
OCR model might *insert* a character $xy$, *delete* the character $\epsilon$, or *replace* the character with another, $y$.

Naively, we assume that these three different types of noise are introduced independently. Hence,
if we let $I$ be the number of insertions, $D$ the number of deletions, and $R$ the number of replacements.

$$\text{Pr}_I, D, R(i, d, r) = \text{Pr}_I(i) \times \text{Pr}_D(d) \times \text{Pr}_R(r)$$

We further make the assumption that the probability of an insertion, deletion, or replacement is independent of the character $x$.

We make use the following probability models to model each different type of noise, where $\text{Po}$ refers to the Poisson distribution.
$$I \sim \text{Po}(\lambda_1)$$
$$D \sim \text{Po}(\lambda_2)$$
$$R \sim \text{Po}(\lambda_3)$$

Given the aforementioned assumptions, and that the Poisson distribution is additive, given a word $w$, we can easily construct models for the noise
$$I_w \ sim \text{Po}(\lambda_1 \times |w|)$$
And symmetrically for the other two cases.

To estimate $\lambda_1, \lambda_2, and \lambda_3$, we performed maximum likelihood estimation on manually labelled outputs of the OCR model, according to the following steps
1. If it is a legitimate field value, then note the true field name, `trueFieldName`. Omit any punctuation, like the colon in "Field Name:", since the formatting may be inconsistent.
2. If it is not, leave the true field name blank.
3. If there are multiple field values corresponding to multiple field names, arbitrarily pick one.
4. If one field value is broken up across multiple identified field names, arbitrarily pick one identified field name. Leave the rest blank.

This allows us to compute $\text{Pr(observed tokens | actual tokens = w)}$ , by computing the $I_w, D_w, R_w$ values for the `(observed tokens, w)` pairs.

With this, we then perform a Bayesian computation to determine $\text{Pr(actual tokens = w | observed tokens)}$.

We then return the maximum a posteriori value, accounting for two edge cases:
1. The desired field name is not in the document - which could occur because of inconsistent formatting or end-user error.
2. The desired field name occurs multiple times in the document.\
By throwing an exception if the posterior values, pre- and post-normalisation respectively, do not meet threshold values.

Having identified the field name, we then perform simple regex matching to extract the numerical value from the string.

If the regex fails to match a value, we throw an exception. 

We then perform various sanity checks on the value to ensure that it is valid - that it has the correct number of decimal places, and that it is not an extreme value.
Neither is cause to throw an exception, but rather to flag to the user that the extraction may not be correct.

Note that $\lambda_1$, $\lambda_2$, $\lambda_3$, the threshold likelihoods, and the desired field name are all specified as runtime variables.

This ensures that the parameters may be continually fine-tuned without re-compiling the code, as well as generalised to other field names.
