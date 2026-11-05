// SPA fallback for the Studio (spec 09 story 19), a CloudFront Function (cloudfront-js-2.0) on the default
// behaviour's viewer requests. A path whose last segment has no file extension is a Studio route, so it is
// served index.html and the Studio's router takes over. Requests for files pass through, so a missing asset is
// still a 404. Only the default behaviour runs this: /api/*, /widget/* and /embed.js are never rewritten.
function handler(event) {
  var request = event.request;
  var lastSegment = request.uri.substring(request.uri.lastIndexOf("/") + 1);
  if (lastSegment.indexOf(".") === -1) {
    request.uri = "/index.html";
  }
  return request;
}
