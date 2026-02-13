from clipserver.media_utils import _parse_content_type, parse_multipart_file


def test_parse_content_type_handles_quoted_boundary():
    media_type, params = _parse_content_type('multipart/form-data; boundary="----abc123"')
    assert media_type == "multipart/form-data"
    assert params["boundary"] == "----abc123"


def test_parse_content_type_handles_empty():
    media_type, params = _parse_content_type("")
    assert media_type == ""
    assert params == {}


def test_parse_multipart_file_browser_style():
    boundary = "----WebKitFormBoundaryABC"
    raw = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="file"; filename="video.mp4"\r\n'
        "Content-Type: video/mp4\r\n\r\n"
        "hello-bytes\r\n"
        f"--{boundary}--\r\n"
    ).encode("utf-8")
    filename, content = parse_multipart_file(
        {"Content-Type": f"multipart/form-data; boundary={boundary}"},
        raw,
    )
    assert filename == "video.mp4"
    assert content == b"hello-bytes"


def test_parse_multipart_file_name_without_quotes():
    boundary = "----b123"
    raw = (
        f"--{boundary}\r\n"
        "Content-Disposition: form-data; name=file; filename=test.mp4\r\n"
        "Content-Type: application/octet-stream\r\n\r\n"
        "abc123\r\n"
        f"--{boundary}--\r\n"
    ).encode("utf-8")
    filename, content = parse_multipart_file(
        {"Content-Type": f"multipart/form-data; boundary={boundary}"},
        raw,
    )
    assert filename == "test.mp4"
    assert content == b"abc123"


def test_parse_multipart_file_accepts_non_file_field_name():
    boundary = "----b124"
    raw = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="upload"; filename="from-browser.mp4"\r\n'
        "Content-Type: application/octet-stream\r\n\r\n"
        "payload\r\n"
        f"--{boundary}--\r\n"
    ).encode("utf-8")
    filename, content = parse_multipart_file(
        {"Content-Type": f"multipart/form-data; boundary={boundary}"},
        raw,
    )
    assert filename == "from-browser.mp4"
    assert content == b"payload"
