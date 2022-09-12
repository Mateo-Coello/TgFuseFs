import os

with open('mnt/file_one', 'w+') as fh1:
    fh1.write('foo')
    fh1.flush()
    with open('mnt/file_one', 'a') as fh2:
        os.unlink('mnt/file_one')
        assert 'file_one' not in os.listdir('mnt')
        fh2.write('bar')
    os.close(os.dup(fh1.fileno()))
    fh1.seek(0)
    assert fh1.read() == 'foobar'
