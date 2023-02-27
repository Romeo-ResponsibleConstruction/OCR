# Extracting Total Weight
Having identified the field name, we then perform simple regex matching to extract the numerical value from the string.

If the regex fails to match a value, we throw an exception. 

We then perform various sanity checks on the value to ensure that it is valid - that it has the correct number of decimal places, and that it is not an extreme value.
Neither is cause to throw an exception, but rather to flag to the user that the extraction may not be correct.