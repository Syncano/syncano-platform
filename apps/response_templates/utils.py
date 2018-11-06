# coding=UTF8
import os


def get_current_virtual_mememory_size(size='vsz'):
    return int(os.popen('ps -p %d -o %s | tail -1' % (os.getpid(), size)).read())
