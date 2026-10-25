import hashlib

from tidyup.duplicates import find_duplicates, sha256_of


def test_sha256_matches_hashlib(tmp_path):
    path = tmp_path / "f.bin"
    path.write_bytes(b"hello")
    assert sha256_of(path) == hashlib.sha256(b"hello").hexdigest()


def test_finds_identical_files_across_folders(inbox, make_file):
    a = make_file(inbox / "a.txt", "same content")
    b = make_file(inbox / "sub" / "b.txt", "same content")
    make_file(inbox / "c.txt", "different!!!")  # same size as the others, different bytes
    make_file(inbox / "unique.txt", "nothing like it")

    assert find_duplicates(inbox) == [[a, b]]


def test_non_recursive(inbox, make_file):
    make_file(inbox / "a.txt", "same")
    make_file(inbox / "sub" / "b.txt", "same")
    assert find_duplicates(inbox, recursive=False) == []


def test_empty_files_are_not_reported(inbox, make_file):
    make_file(inbox / "empty1", "")
    make_file(inbox / "empty2", "")
    assert find_duplicates(inbox) == []
