export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const fileId = url.searchParams.get("file_id");

    if (!fileId) return new Response("Missing file_id", { status: 400 });

    const token = env.TG_TOKEN;
    if (!token) return new Response("TG_TOKEN not set", { status: 500 });

    try {
      // Step 1: getFile → dapat file_path
      const infoResp = await fetch(
        `https://api.telegram.org/bot${token}/getFile?file_id=${encodeURIComponent(fileId)}`
      );
      const info = await infoResp.json();
      if (!info.ok) return new Response(JSON.stringify(info), { status: 400 });

      const filePath = info.result.file_path;

      // Step 2: download file dan return ke caller
      const fileResp = await fetch(
        `https://api.telegram.org/file/bot${token}/${filePath}`
      );
      const contentType = fileResp.headers.get("Content-Type") || "image/jpeg";
      const bytes = await fileResp.arrayBuffer();

      return new Response(bytes, {
        headers: { "Content-Type": contentType },
      });
    } catch (err) {
      return new Response(`Error: ${err.message}`, { status: 500 });
    }
  },
};
