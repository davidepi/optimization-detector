from __future__ import annotations

import hashlib
import heapq
import os
import random
from typing import BinaryIO, Optional, List

HEADER_SIZE = 8
MAGIC = 0x27
BLOCK_SIZE = 4194304


class BinaryDs:
    """
    Class used to contain a dataset in a binary form, where each example
    belongs to a given category.

    File structure of the binary:
    1 bytes -> magic
    1 bytes -> 0: data is opcode based, 1:data is raw based
    2 bytes -> number of features for each example
    4 bytes -> number of examples
    All the examples in the form {label(1 byte)+data}
    """

    def __init__(self, path: str, read_only: bool = False,
                 features: int = 2048, raw_data: bool = True) -> None:
        """
        Constructor

        :param path: path to the binary dataset
        :param read_only: True if the dataset will be open in read only mode
        :param features: number of features that will be used for each example
        :param raw_data: true if the contained data will be a raw dump, so not
        an opcode based encoding.
        (This has no effect on the dataset itself, but it is used as a double
        check to avoid mixing data from dataset encoded in different ways)
        """
        self.magic: int = MAGIC
        self.raw: bool = raw_data
        self.path: str = path
        self.features: int = features
        self.examples: int = 0
        self.ro: bool = read_only
        self.file: Optional[BinaryIO] = None

    def open(self) -> BinaryDs:
        """
        Opens a Binary dataset for editing. Creates it if not existing iff
        read_only was set to False in the constructor.
        :return: The created dataset
        """
        if not os.path.exists(self.path):
            if self.ro:
                raise PermissionError("Could not create file (Read only flag)")
            else:
                self.file = open(self.path, "wb+")
                self.file.write(self.magic.to_bytes(1, byteorder="little"))
                self.file.write(self.raw.to_bytes(1, byteorder="little"))
                self.file.write(self.features.to_bytes(2, byteorder="little"))
                self.file.write(self.examples.to_bytes(4, byteorder="little"))
        elif self.ro and os.access(self.path, os.R_OK):
            self.file = open(self.path, "rb")
            self.__read_and_check_existing()
        elif not self.ro and os.access(self.path, os.W_OK):
            self.file = open(self.path, "rb+")
            self.__read_and_check_existing()
        else:
            raise PermissionError()
        return self

    def close(self) -> None:
        """
        Closes an open dataset.
        """
        if self.file:
            self.file.close()
            self.file = None

    def __enter__(self):
        return self.open()

    def __exit__(self, exc_type, exc_value, tb):
        self.close()

    def __read_and_check_existing(self) -> None:
        # Reads the data from the existing dataset file
        # Checks for consistency with the expected encoding and feature size
        # If the file is open for reading, just update features and encoding
        self.file.seek(0, os.SEEK_SET)
        if int.from_bytes(self.file.read(1), byteorder="little") != MAGIC:
            self.file.close()
            self.file = None
            raise IOError(f"File {self.path} was not created by this "
                          f"application.")
        raw = int.from_bytes(self.file.read(1), byteorder="little")
        features = int.from_bytes(self.file.read(2), byteorder="little")
        self.examples = int.from_bytes(self.file.read(4), byteorder="little")
        # consistency check
        if not self.ro and self.raw != raw:
            self.file.close()
            self.file = None
            raise IOError("The existing file has a different encoding type")
        else:
            self.raw = raw
        if not self.ro and self.features != features:
            self.file.close()
            self.file = None
            raise IOError("The existing file has a different number of "
                          "features")
        else:
            self.features = features

    def is_raw(self) -> bool:
        """
        Returns the type of encoding used on the file.
        1 for Raw based, 0 for Opcode based
        """
        return self.raw

    def get_features(self) -> int:
        """
        Returns the number of features used in the dataset.
        """
        return self.features

    def get_examples_no(self) -> int:
        """
        Returns the number of examples contained in the dataset.
        """
        return self.examples

    def write(self, data: List[(int, bytes)]) -> None:
        """
        Writes a list of examples in the file.
        Throws ValueError if the tuple has a different length compared to the
        one passed in the constructor.
        :param data: A tuple (category id, data) that will be written.
        """
        for val in data:
            if len(val[1]) != self.features:
                raise ValueError("The input example has a wrong length")
        offset = HEADER_SIZE + (self.features + 1) * self.examples
        self.examples += len(data)
        self.file.seek(4, os.SEEK_SET)
        self.file.write(self.examples.to_bytes(4, byteorder="little"))
        self.file.seek(offset, os.SEEK_SET)
        for val in data:
            self.file.write(val[0].to_bytes(1, byteorder="little"))
            self.file.write(val[1])

    def read(self, index: int, amount: int = 1) -> List[(int, bytes)]:
        """
        Reads some examples from the dataset.
        Raises IndexError if index+amount is higher than the number of
        available examples.
        :param index: The starting index of the examples to read (0-based)
        :param amount: The number of examples that will be read
        :return: A list of tuples (category id, data), each tuple being an
        example
        """
        if index + amount > self.examples:
            raise IndexError
        else:
            retval = []
            offset = HEADER_SIZE + (self.features + 1) * index
            self.file.seek(offset, os.SEEK_SET)
            for i in range(0, amount):
                cat = int.from_bytes(self.file.read(1), byteorder="little")
                data = self.file.read(self.features)
                retval.append((cat, data))
            return retval

    def shuffle(self, seed=None) -> None:
        """
        Shuffles in place the dataset.
        :param seed: Seed that will be used for the RNG
        """
        random.seed(seed)
        for j_index in range(self.examples)[::-1]:
            k_index = int(random.random() * j_index)
            if j_index != k_index:
                offset_j = HEADER_SIZE + (self.features + 1) * j_index
                self.file.seek(offset_j, os.SEEK_SET)
                j = self.file.read(self.features + 1)
                offset_k = HEADER_SIZE + (self.features + 1) * k_index
                self.file.seek(offset_k, os.SEEK_SET)
                k = self.file.read(self.features + 1)
                self.file.seek(offset_k, os.SEEK_SET)
                self.file.write(j)
                self.file.seek(offset_j, os.SEEK_SET)
                self.file.write(k)

    def balance(self) -> None:
        """
        Balances the dataset. This method will use less memory and be more
        efficient when the dataset is randomized.
        """
        cats = []
        # use counting sort to record how many examples for each class
        self.file.seek(HEADER_SIZE, os.SEEK_SET)
        for i in range(self.examples):
            data = self.file.read(self.features + 1)
            cat = data[0]
            while len(cats) <= cat:
                cats.append(0)
            cats[cat] += 1
        if len(cats) == 0 or len(cats) == 1:
            return  # no point in balancing when there's nothing
        minval = min(cats)
        cats = [x - minval for x in cats]
        stored = []
        # now: remove examples from the end and store them in memory until
        # balance is reached, throwing away the unbalanced ones. Then write
        # back the one in memory.
        # this is n^2 under the assumption that categories are small
        self.file.seek(0, os.SEEK_END)
        while sum(cats) != 0:
            self.file.seek(-self.features - 1, os.SEEK_CUR)
            data = self.file.read(self.features + 1)
            self.file.seek(-self.features - 1, os.SEEK_CUR)
            if cats[data[0]] == 0:
                # need this example for balance
                stored.append((data[0], data[1:]))
            else:
                cats[data[0]] -= 1  # throw example away
            self.examples -= 1
        self.write(stored)

    def truncate(self, left=0) -> None:
        """
        Remove all examples from file
        """
        feature_size = self.features + 1
        self.file.truncate(HEADER_SIZE + feature_size * left)
        self.file.seek(4, os.SEEK_SET)
        self.examples = left
        self.file.write(self.examples.to_bytes(4, byteorder="little"))

    def merge(self, other: BinaryDs) -> None:
        """
        Removes all the content from other and puts it into self
        """
        if self.is_raw() != other.is_raw():
            raise IOError("To merge two datasets they must have the same "
                          "encoding")
        if self.get_features() != other.get_features():
            raise IOError("To merge two datasets they must have the same "
                          "features")
        examples_no = other.examples
        features_size = self.features + 1
        amount = int(BLOCK_SIZE / features_size)
        iterations = int(examples_no / amount)
        for i in range(iterations):
            read = other.read(i * amount, amount)
            self.write(read)
        remainder = examples_no % amount
        if remainder > 0:
            read = other.read(iterations, remainder)
            self.write(read)
        # remove from other file and update elements amount
        other.truncate()

    def split(self, other: BinaryDs, ratio: float) -> None:
        """
        Removes part of self and put it to other.
        The variable ration is #examples_kept/#examples_given
        """
        if self.is_raw() != other.is_raw():
            raise IOError("To merge two datasets they must have the same "
                          "encoding")
        if self.get_features() != other.get_features():
            raise IOError("To merge two datasets they must have the same "
                          "features")

        examples_no = int(self.examples * ratio)
        features_size = self.features + 1
        amount = int(BLOCK_SIZE / features_size)
        iterations = int(self.examples / amount)
        for _ in range(iterations):
            read = self.read(self.examples - amount, amount)
            other.write(read)
            self.truncate(self.examples - amount)
        remainder = examples_no % amount
        if remainder > 0:
            read = self.read(self.examples - remainder, remainder)
            other.write(read)
            self.truncate(self.examples - remainder)

    def deduplicate(self) -> None:
        """
        Removes all duplicates from the current binary.
        The order of data may change.
        This has a unlikely small chance of removing elements that are not
        duplicates, but this is a dataset and not a database so who cares ;)
        """
        feature_size = self.features + 1
        chunk_size = BLOCK_SIZE + feature_size  # around 4 MiB ;)
        chunk_size = int(chunk_size - (chunk_size % feature_size))
        chunk_elements = int(chunk_size / feature_size)
        chunks_no = int(self.examples / chunk_elements)
        hashes = set()
        remove = []
        chunk_index = 0
        heapq.heapify(remove)
        for _ in range(chunks_no):
            self.__calculate_hashes_from_chunk(chunk_elements, chunk_index,
                                               hashes, remove)
            chunk_index += 1
        remainder = self.examples % chunk_elements
        if remainder > 0:
            self.__calculate_hashes_from_chunk(remainder, chunk_index,
                                               hashes, remove)
        del hashes
        # actual removal (pop element from the end, replace first index)
        while len(remove) != 0:
            index = heapq.heappop(remove)
            if index == self.examples - 1:
                # element to remove is the last one, just remove it
                self.examples -= 1
                self.file.truncate(HEADER_SIZE + feature_size * self.examples)
                self.file.seek(4, os.SEEK_SET)
                self.file.write(self.examples.to_bytes(4, byteorder="little"))
            else:
                # read last element, remove it and overwrite duplicate
                self.file.seek(
                    HEADER_SIZE + feature_size * (self.examples - 1),
                    os.SEEK_SET)
                data = self.file.read(feature_size)
                self.examples -= 1
                self.file.truncate(HEADER_SIZE + feature_size * self.examples)
                self.file.seek(HEADER_SIZE + index * feature_size, os.SEEK_SET)
                self.file.write(data)
                self.file.seek(4, os.SEEK_SET)
                self.file.write(self.examples.to_bytes(4, byteorder="little"))

    def __calculate_hashes_from_chunk(self, chunk_elements, chunk_index,
                                      hashes, remove):
        # internal method used in the deduplicate function
        data = self.read(chunk_index * chunk_elements, chunk_elements)
        for count, elem in enumerate(data):
            index = chunk_index * chunk_elements + count
            cur_hash = hashlib.md5(elem[1]).digest()
            if cur_hash in hashes:
                heapq.heappush(remove, index)
            else:
                hashes.add(cur_hash)
