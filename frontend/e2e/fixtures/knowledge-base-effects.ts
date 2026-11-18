import { crc32, deflateSync } from "node:zlib";

/**
 * Files built in memory for the Knowledge Base effects spec (`tests/knowledge-base-effects.spec.ts`):
 * a slide deck, whose Chunks carry page numbers (a slide is a page to Docling), and a scanned PDF,
 * whose only page is an image of text.
 */

/** One file in a zip, stored uncompressed. */
interface Entry {
  name: string;
  data: Buffer;
}

/** A zip archive with every entry stored (no compression), which is all an Office file needs. */
function zip(entries: Entry[]): Buffer {
  const locals: Buffer[] = [];
  const centrals: Buffer[] = [];
  let offset = 0;
  for (const { name, data } of entries) {
    const fileName = Buffer.from(name, "utf8");
    const crc = crc32(data);
    const local = Buffer.alloc(30);
    local.writeUInt32LE(0x04034b50, 0);
    local.writeUInt16LE(20, 4);
    local.writeUInt16LE(0, 6);
    local.writeUInt16LE(0, 8);
    local.writeUInt32LE(0, 10);
    local.writeUInt32LE(crc, 14);
    local.writeUInt32LE(data.length, 18);
    local.writeUInt32LE(data.length, 22);
    local.writeUInt16LE(fileName.length, 26);
    local.writeUInt16LE(0, 28);
    locals.push(local, fileName, data);
    const central = Buffer.alloc(46);
    central.writeUInt32LE(0x02014b50, 0);
    central.writeUInt16LE(20, 4);
    central.writeUInt16LE(20, 6);
    central.writeUInt16LE(0, 8);
    central.writeUInt16LE(0, 10);
    central.writeUInt32LE(0, 12);
    central.writeUInt32LE(crc, 16);
    central.writeUInt32LE(data.length, 20);
    central.writeUInt32LE(data.length, 24);
    central.writeUInt16LE(fileName.length, 28);
    central.writeUInt32LE(offset, 42);
    centrals.push(central, fileName);
    offset += local.length + fileName.length + data.length;
  }
  const directory = Buffer.concat(centrals);
  const end = Buffer.alloc(22);
  end.writeUInt32LE(0x06054b50, 0);
  end.writeUInt16LE(entries.length, 8);
  end.writeUInt16LE(entries.length, 10);
  end.writeUInt32LE(directory.length, 12);
  end.writeUInt32LE(offset, 16);
  return Buffer.concat([...locals, directory, end]);
}

const P = "http://schemas.openxmlformats.org/presentationml/2006/main";
const A = "http://schemas.openxmlformats.org/drawingml/2006/main";
const R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships";
const REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships";
const PKG = "http://schemas.openxmlformats.org/package/2006/relationships";
const XML = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n';

function escapeXml(text: string): string {
  return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function relationships(items: { id: string; type: string; target: string }[]): string {
  return `${XML}<Relationships xmlns="${PKG}">${items
    .map(({ id, type, target }) => `<Relationship Id="${id}" Type="${REL}/${type}" Target="${target}"/>`)
    .join("")}</Relationships>`;
}

const GROUP = `<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>`;

function shape(id: number, name: string, placeholder: string, text: string, y: number): string {
  return (
    `<p:sp><p:nvSpPr><p:cNvPr id="${String(id)}" name="${name}"/><p:cNvSpPr/><p:nvPr>${placeholder}</p:nvPr></p:nvSpPr>` +
    `<p:spPr><a:xfrm><a:off x="457200" y="${String(y)}"/><a:ext cx="8229600" cy="1143000"/></a:xfrm></p:spPr>` +
    `<p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:r><a:rPr lang="en-GB"/><a:t>${escapeXml(text)}</a:t></a:r></a:p></p:txBody></p:sp>`
  );
}

function slideXml(title: string, body: string): string {
  return (
    `${XML}<p:sld xmlns:a="${A}" xmlns:r="${R}" xmlns:p="${P}"><p:cSld><p:spTree>${GROUP}` +
    shape(2, "Title 1", '<p:ph type="title"/>', title, 274638) +
    shape(3, "Content 2", '<p:ph idx="1"/>', body, 1600200) +
    `</p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sld>`
  );
}

const THEME =
  `${XML}<a:theme xmlns:a="${A}" name="Plain"><a:themeElements>` +
  `<a:clrScheme name="Plain"><a:dk1><a:srgbClr val="000000"/></a:dk1><a:lt1><a:srgbClr val="FFFFFF"/></a:lt1>` +
  `<a:dk2><a:srgbClr val="1F497D"/></a:dk2><a:lt2><a:srgbClr val="EEECE1"/></a:lt2><a:accent1><a:srgbClr val="4F81BD"/></a:accent1>` +
  `<a:accent2><a:srgbClr val="C0504D"/></a:accent2><a:accent3><a:srgbClr val="9BBB59"/></a:accent3><a:accent4><a:srgbClr val="8064A2"/></a:accent4>` +
  `<a:accent5><a:srgbClr val="4BACC6"/></a:accent5><a:accent6><a:srgbClr val="F79646"/></a:accent6><a:hlink><a:srgbClr val="0000FF"/></a:hlink>` +
  `<a:folHlink><a:srgbClr val="800080"/></a:folHlink></a:clrScheme>` +
  `<a:fontScheme name="Plain"><a:majorFont><a:latin typeface="Calibri"/><a:ea typeface=""/><a:cs typeface=""/></a:majorFont>` +
  `<a:minorFont><a:latin typeface="Calibri"/><a:ea typeface=""/><a:cs typeface=""/></a:minorFont></a:fontScheme>` +
  `<a:fmtScheme name="Plain"><a:fillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:fillStyleLst>` +
  `<a:lnStyleLst><a:ln w="9525"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln><a:ln w="9525"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln><a:ln w="9525"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln></a:lnStyleLst>` +
  `<a:effectStyleLst><a:effectStyle><a:effectLst/></a:effectStyle><a:effectStyle><a:effectLst/></a:effectStyle><a:effectStyle><a:effectLst/></a:effectStyle></a:effectStyleLst>` +
  `<a:bgFillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:bgFillStyleLst>` +
  `</a:fmtScheme></a:themeElements></a:theme>`;

const MASTER =
  `${XML}<p:sldMaster xmlns:a="${A}" xmlns:r="${R}" xmlns:p="${P}"><p:cSld><p:spTree>${GROUP}</p:spTree></p:cSld>` +
  `<p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" accent2="accent2" accent3="accent3" accent4="accent4" accent5="accent5" accent6="accent6" hlink="hlink" folHlink="folHlink"/>` +
  `<p:sldLayoutIdLst><p:sldLayoutId id="2147483649" r:id="rId1"/></p:sldLayoutIdLst>` +
  `<p:txStyles><p:titleStyle/><p:bodyStyle/><p:otherStyle/></p:txStyles></p:sldMaster>`;

const LAYOUT =
  `${XML}<p:sldLayout xmlns:a="${A}" xmlns:r="${R}" xmlns:p="${P}" type="obj"><p:cSld name="Title and Content"><p:spTree>${GROUP}</p:spTree></p:cSld>` +
  `<p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sldLayout>`;

/**
 * A slide deck (.pptx) with one titled slide per entry. Docling reads each slide as a page, so the
 * Chunks it makes say which slide ("Page 2") their text is on.
 */
export function slideDeck(name: string, slides: { title: string; body: string }[]) {
  const slideTypes = slides
    .map(
      (_, index) =>
        `<Override PartName="/ppt/slides/slide${String(index + 1)}.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>`,
    )
    .join("");
  const contentTypes =
    `${XML}<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">` +
    `<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>` +
    `<Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>` +
    `<Override PartName="/ppt/slideMasters/slideMaster1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/>` +
    `<Override PartName="/ppt/slideLayouts/slideLayout1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/>` +
    `<Override PartName="/ppt/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/>` +
    `${slideTypes}</Types>`;
  const presentation =
    `${XML}<p:presentation xmlns:a="${A}" xmlns:r="${R}" xmlns:p="${P}">` +
    `<p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/></p:sldMasterIdLst>` +
    `<p:sldIdLst>${slides.map((_, index) => `<p:sldId id="${String(256 + index)}" r:id="rId${String(index + 3)}"/>`).join("")}</p:sldIdLst>` +
    `<p:sldSz cx="9144000" cy="6858000"/><p:notesSz cx="6858000" cy="9144000"/></p:presentation>`;
  const entries: Entry[] = [
    { name: "[Content_Types].xml", data: Buffer.from(contentTypes) },
    { name: "_rels/.rels", data: Buffer.from(relationships([{ id: "rId1", type: "officeDocument", target: "ppt/presentation.xml" }])) },
    { name: "ppt/presentation.xml", data: Buffer.from(presentation) },
    {
      name: "ppt/_rels/presentation.xml.rels",
      data: Buffer.from(
        relationships([
          { id: "rId1", type: "slideMaster", target: "slideMasters/slideMaster1.xml" },
          { id: "rId2", type: "theme", target: "theme/theme1.xml" },
          ...slides.map((_, index) => ({ id: `rId${String(index + 3)}`, type: "slide", target: `slides/slide${String(index + 1)}.xml` })),
        ]),
      ),
    },
    { name: "ppt/slideMasters/slideMaster1.xml", data: Buffer.from(MASTER) },
    {
      name: "ppt/slideMasters/_rels/slideMaster1.xml.rels",
      data: Buffer.from(
        relationships([
          { id: "rId1", type: "slideLayout", target: "../slideLayouts/slideLayout1.xml" },
          { id: "rId2", type: "theme", target: "../theme/theme1.xml" },
        ]),
      ),
    },
    { name: "ppt/slideLayouts/slideLayout1.xml", data: Buffer.from(LAYOUT) },
    {
      name: "ppt/slideLayouts/_rels/slideLayout1.xml.rels",
      data: Buffer.from(relationships([{ id: "rId1", type: "slideMaster", target: "../slideMasters/slideMaster1.xml" }])),
    },
    { name: "ppt/theme/theme1.xml", data: Buffer.from(THEME) },
    ...slides.flatMap(({ title, body }, index) => [
      { name: `ppt/slides/slide${String(index + 1)}.xml`, data: Buffer.from(slideXml(title, body)) },
      {
        name: `ppt/slides/_rels/slide${String(index + 1)}.xml.rels`,
        data: Buffer.from(relationships([{ id: "rId1", type: "slideLayout", target: "../slideLayouts/slideLayout1.xml" }])),
      },
    ]),
  ];
  return {
    name,
    mimeType: "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    buffer: zip(entries),
  };
}

/**
 * A one-page scanned PDF: the page is a greyscale image (`pixels`, one byte a pixel, rows top
 * first) with no text layer, so only OCR can read what it shows.
 */
export function scannedPdf(name: string, pixels: Buffer, width: number, height: number) {
  const image = deflateSync(pixels);
  // 150 dots per inch, in PDF points (72 an inch).
  const [w, h] = [Math.round((width * 72) / 150), Math.round((height * 72) / 150)];
  const draw = Buffer.from(`q ${String(w)} 0 0 ${String(h)} 0 0 cm /Im0 Do Q`);
  const objects: Buffer[] = [
    Buffer.from("<< /Type /Catalog /Pages 2 0 R >>"),
    Buffer.from("<< /Type /Pages /Kids [3 0 R] /Count 1 >>"),
    Buffer.from(`<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${String(w)} ${String(h)}] /Resources << /XObject << /Im0 4 0 R >> >> /Contents 5 0 R >>`),
    Buffer.concat([
      Buffer.from(
        `<< /Type /XObject /Subtype /Image /Width ${String(width)} /Height ${String(height)} /ColorSpace /DeviceGray /BitsPerComponent 8 /Filter /FlateDecode /Length ${String(image.length)} >>\nstream\n`,
      ),
      image,
      Buffer.from("\nendstream"),
    ]),
    Buffer.concat([Buffer.from(`<< /Length ${String(draw.length)} >>\nstream\n`), draw, Buffer.from("\nendstream")]),
  ];
  const header = Buffer.from("%PDF-1.4\n%\xe2\xe3\xcf\xd3\n", "latin1");
  const parts: Buffer[] = [header];
  let offset = header.length;
  const offsets: number[] = [];
  objects.forEach((body, index) => {
    offsets.push(offset);
    const object = Buffer.concat([Buffer.from(`${String(index + 1)} 0 obj\n`), body, Buffer.from("\nendobj\n")]);
    parts.push(object);
    offset += object.length;
  });
  const xref =
    `xref\n0 ${String(objects.length + 1)}\n0000000000 65535 f \n` +
    offsets.map((at) => `${String(at).padStart(10, "0")} 00000 n \n`).join("") +
    `trailer\n<< /Size ${String(objects.length + 1)} /Root 1 0 R >>\nstartxref\n${String(offset)}\n%%EOF\n`;
  parts.push(Buffer.from(xref));
  return { name, mimeType: "application/pdf", buffer: Buffer.concat(parts) };
}
