enum curve : u8 {
    unkown,
    xRGB,
    gamma2,
    linear,
    offset_log,
    sRGB
};

import std.string;
using SizedString<T> = std::string::SizedString16<T>;
using NullString = std::string::NullString;

struct string {
NullString strings;
curve curve;
};

string string[11866] @0x00;