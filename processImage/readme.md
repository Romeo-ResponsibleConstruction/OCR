# Processing the Image
The `processImage` code expects an image to be uploaded in the `gpr_images` bucket.

The image can be in a `png`, `jpg` or  `jpeg` format.

It then calls Google Cloud Platform's document parse OCR processor, extracts the `field name` and 
`field value` pairs, as well as their corresponding likelihoods, and populates a `csv` file with these values.