/** Add a photo to a multipart form: the uri is a blob:/data: URL, read it into a Blob. */
export async function appendPhoto(form: FormData, field: string, uri: string) {
  const blob = await (await fetch(uri)).blob();
  form.append(field, blob, `${field}.jpg`);
}
