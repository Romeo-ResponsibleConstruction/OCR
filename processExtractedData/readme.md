# Processing the Extracted Data 
**Goal**: To extract the desired field values for each field name specified by the user, flagging when this cannot be done.

**Problem**: The OCR model might introduce corruption, in the form of insertions, deletions, and replacements.
For example, starting with the string "Total Weight", the OCR model might extract "Total Weight:", "Total Weigh", or "Total Wejght" respectively.

**Solution**: Build a probability model for noise and choose the maximum a posteriori value as the "matched field name".

### Probability Model for Matching Field Names
Consider the Levenshtein Distance $L$, which is computed as the minimum number of insertions $I$, deletions $D$ and replacements $R$ needed to 
convert one string $s_1$ into another string $s_2$

Now consider an arbitrary character $x$. We model *noise* introduced by the OCR system as insertions, deletions, or replacements, since the 
OCR model might *insert* a character $xy$, *delete* the character $\epsilon$, or *replace* the character with another, $y$.

Naively, we assume that these three different types of noise are introduced independently. Hence,
if we let $I$ be the number of insertions, $D$ the number of deletions, and $R$ the number of replacements.

$$\text{Pr}_I, D, R(i, d, r) = \text{Pr}_I(i) \times \text{Pr}_D(d) \times \text{Pr}_R(r)$$

We further make the assumption that the probability of an insertion, deletion, or replacement is independent of the character $x$, and any inserted/replaced characters.

We make use the following probability models to model each different type of noise, where $\text{Po}$ refers to the Poisson distribution.
$$I \sim \text{Po}(\lambda_1)$$
$$D \sim \text{Po}(\lambda_2)$$
$$R \sim \text{Po}(\lambda_3)$$

In order to estimate this, we performed a maximum likelihood estimation on some training data. Details may be found in `./dataAnalysis`
Given the aforementioned assumptions, and that the Poisson distribution is additive, given a word $w$, we can easily construct models for the noise
$$I_w \sim \text{Po}(\lambda_1 \times |w|)$$
And symmetrically for the other two cases.

This allows us to compute $\text{Pr(observed tokens | actual tokens = w)}$ , by computing the $I_w, D_w, R_w$ values for the `(observed tokens, w)` pairs.

With this, we then perform a Bayesian computation to determine $\text{Pr(actual tokens = w | observed tokens)}$.

We then return the maximum a posteriori value, accounting for two edge cases:
1. The desired field name is not in the document - which could occur because of inconsistent formatting or end-user error.
2. The desired field name occurs multiple times in the document.\
By throwing an exception if the posterior values, pre- and post-normalisation respectively, do not meet threshold values.

Note that $\lambda_1$, $\lambda_2$, $\lambda_3$, the threshold likelihoods, and the desired field name are all specified as runtime variables.

This ensures that the parameters may be continually fine-tuned without re-compiling the code, as well as generalised to other field names.

### Matching Field Values
We create a `returnObject`. For each `(fieldName, functionName)` tuple in the list of Fields provided by the user, we use the probability model defined above to
1. Attempt to match an extracted field name, handling an exception by updating `returnObject[fieldName]`
2. If we can match an extracted field name, we create a temporary Topic and a temporary Subscription to that Topic.
3. We then pass the `matchedFieldValue` string and the topic name `topic` to the function specified by `functionName`, creating a Promise in doing so. _(For more information about what the function does, see_ `./extractValue` _)_
4. Asynchronously, if the function terminates within the timeout, we take the payload of its return value and save it in `returnObject[fieldName]`
5. If not, we record a timeout error in `returnObject[fieldName]`.
Finally, we delete the Topic and Subscription, and save `returnObject` to a `.json` file in the `gpr_sanitised_data` bucket.