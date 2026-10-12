import { File } from 'expo-file-system';

/** Add a photo to a multipart form. expo/fetch (the global fetch) only takes Blob/File parts: wrap the file. */
export async function appendPhoto(form: FormData, field: string, uri: string) {
  form.append(field, new File(uri));
}
