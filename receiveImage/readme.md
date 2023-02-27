# Receiving the Image
The `receiveImage` code performs the following steps.

First, it validates the file format of input. Throws an exception if the format is not jpeg, jpg, or png.

Checks if there exists a valid mapping from the filename to some `mappedFileName` in the `mapping.json` file in the `gpr_auxiliary` bucket.

If there does, use the corresponding Y.

If not, create a UUID Y, add it to the `mapping.json file`.

Saves (potentially overwrite) Y.exn in `gpr_images`.