# Extracting Values
A collection of user-defined functions for extracting values.

All functions must accept a payload with `topic` and `valueString`.

All functions must return a value with body that meets the specification outlined in `.databaseUpload`, by publishing to the Topic with name `topic`. 