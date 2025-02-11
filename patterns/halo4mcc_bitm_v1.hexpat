enum curve : u32 {
    unkown,
    xRGB,
    gamma2,
    linear,
    offset_log,
    sRGB
};


struct data {
padding [72];
u32 skip;
padding[skip - 123];
curve curve;
};

data data @ 0x00;