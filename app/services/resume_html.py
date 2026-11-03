"""Bounded HTML cleanup; preview is additionally served in a CSP sandbox."""

from html import escape
from html.parser import HTMLParser
import re

from app.core.errors import AppError

PREVIEW_CSP = "sandbox; default-src 'none'; script-src 'none'; style-src 'unsafe-inline'; img-src 'none'; font-src 'none'; connect-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
ALLOWED = set("html head body title style main section article header footer div span h1 h2 h3 h4 h5 h6 p strong em b i u small br hr ul ol li dl dt dd table thead tbody tfoot tr th td colgroup col blockquote address time a sup sub".split())
VOID = {"br", "hr", "col"}
DROP = {"script", "iframe", "object", "embed", "svg", "math", "template", "noscript", "form", "button", "textarea", "select", "video", "audio"}
ATTRS = {"class", "id", "style", "lang", "dir", "colspan", "rowspan", "aria-label"}


class PreviewParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.output, self.text = [], []
        self.blocked = []
        self.in_style = False

    def handle_starttag(self, tag, attrs):
        if self.blocked:
            if tag in DROP and tag not in {"embed"}:
                self.blocked.append(tag)
            return
        if tag in DROP:
            if tag != "embed":
                self.blocked.append(tag)
            return
        if tag in ALLOWED:
            clean = [(name, value) for name, value in attrs if name in ATTRS and value is not None]
            self.output.append("<" + tag + "".join(f' {name}="{escape(value, quote=True)}"' for name, value in clean) + ">")
            self.in_style = tag == "style" or self.in_style

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if self.blocked:
            if tag == self.blocked[-1]:
                self.blocked.pop()
            return
        if tag in ALLOWED and tag not in VOID:
            self.output.append("</" + tag + ">")
        if tag == "style":
            self.in_style = False

    def handle_data(self, data):
        if not self.blocked:
            self.output.append(data if self.in_style else escape(data))
            if not self.in_style:
                self.text.append(data)


def prepare_html(raw: str, personal: dict) -> str:
    raw = re.sub(r"^```(?:html)?\s*|\s*```$", "", raw.strip(), flags=re.IGNORECASE)
    if not re.match(r"(?:<!doctype\s+html[^>]*>\s*)?<html\b", raw, flags=re.IGNORECASE) or not re.search(r"</html>\s*$", raw, flags=re.IGNORECASE):
        raise AppError(502, "GENERATION_HTML_INVALID", "模型未返回完整 HTML 页面，请重试生成。")
    parser = PreviewParser()
    parser.feed(raw)
    parser.close()
    text = re.sub(r"\s+", "", " ".join(parser.text))
    if len(text) < 10 or "<body" not in raw.lower() or "<style" not in raw.lower() or not text:
        raise AppError(502, "GENERATION_HTML_INVALID", "模型返回的简历正文或排版样式不完整，请重试。")
    for field in ("name", "phone", "email"):
        expected = re.sub(r"\s+", "", personal.get(field) or "")
        if expected and expected not in text:
            raise AppError(502, "GENERATION_FACT_CHANGED", "生成结果遗漏或修改了姓名/联系方式，请重试生成；原表单已保留。")
    document = "<!DOCTYPE html>\n" + "".join(parser.output)
    head = re.search(r"<head\b[^>]*>", document, flags=re.IGNORECASE)
    meta = '<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
    if head:
        document = document[:head.end()] + meta + document[head.end():]
    else:
        document = re.sub(r"(<html\b[^>]*>)", r"\1<head>" + meta + "</head>", document, count=1, flags=re.IGNORECASE)
    return document
