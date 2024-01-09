from optparse import OptionParser
from PIL import Image
import numpy as np

def main():
    usage = "usage: %prog [options] arg ..."
    parser = OptionParser(usage)
    parser.set_defaults(output="stack.fit")
#    parser.set_defaults(overwrite=False)

    parser.add_option("--output", dest="output",help="Mean filename")
#    parser.add_option("--overwrite",
#                      action="store_true", dest="overwrite", help="Overwrite output files")

    (options, args) = parser.parse_args()

    if len(args) < 1:
        parser.error("incorrect number of arguments")


    stack=None

    for filename in args:
        img = Image.open(filename)
        d=np.asarray(img)

        if stack is None:
            stack=d
        else:
            stack=np.max([d,stack],axis=0)

    im = Image.fromarray(stack)
    im.save(options.output)


if __name__ == "__main__":
    main()

