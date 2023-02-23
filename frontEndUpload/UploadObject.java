import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.BlobInfo;
import com.google.cloud.storage.Storage;
import com.google.cloud.storage.StorageOptions;
import com.google.cloud.storage.StorageException;

import java.io.IOException;
import java.nio.file.Paths;


/* Maven Dependencies:
    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>com.google.cloud</groupId>
                <artifactId>libraries-bom</artifactId>
                <version>26.8.0</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
    <dependency>
        <groupId>com.google.cloud</groupId>
        <artifactId>google-cloud-storage</artifactId>
    </dependency>
    </dependencies>
 */


/* Gradle Dependencies:
implementation platform('com.google.cloud:libraries-bom:26.8.0')
implementation 'com.google.cloud:google-cloud-storage'
 */


public class UploadObject {

    public static void upload_object(
            String objectName, String filePath, String bucketName)
            throws IOException {

        StorageOptions storageOpt = StorageOptions.getUnauthenticatedInstance();
        Storage storage = storageOpt.getService();

        BlobId blobId = BlobId.of(bucketName, objectName);

        // Unlikely to need to set another option for PNG types
        BlobInfo blobInfo = BlobInfo.newBuilder(blobId).setContentType("image/jpeg").build();

        try {
            storage.createFrom(blobInfo, Paths.get(filePath));
        }
        catch (StorageException e) {
            // Catch cloud storage exception - can be thrown when disconnected
            throw new IOException(e);
        }
    }
}
