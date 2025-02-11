// Created by Brooen, EonZeNx

#pragma pattern_limit 99999999999
#pragma array_limit 9999999999999
#pragma allow_edits

import std.io;
import std.string;
import type.base;

using NullString = std::string::NullString;
using SizedString<T> = std::string::SizedString16<T>;

enum BlendModes : u8 {
  Opaque,
  Additive,
  Multiply,
  Alpha_Blend,
  Double_Multiply,
  Pre_Multiplied_Alpha,
  Maximum,
  Multiply_Add,
  Add_Source_Times_Destination_Alpha,
  Add_Source_Times_Source_Alpha,
  Inv_Alpha_Blend,
  Motion_Blur_Static,
  Motion_Blur_Inhibit,
  Apply_Shadow_Into_Shadow_Mask,
  Alpha_Blend_Constant,
  Overdraw_Apply,
  Wet_Screen_Effect,
  Minimum,
  Reverse_Subtract,
  Forge_Lightmap,
  Forge_Lightmap_Inv,
  Replace_All_Channels,
  Alpha_Blend_Max,
  Opaque_Alpha_Blend,
  Alpha_Blend_Additive_Transparent
};

enum TransparentShadowPolicies : u32 {
  None,
  Render_as_decal,
  Render_with_material,
};

enum ParameterType : u32 {
    bitmap,
    real,
    int,     
    boolean, 
    color
};

enum WrapMode : u16 {
    wrap,
    clamp,
    mirror,
    black_border,
    mirror_once,
    mirror_once_border
};

enum FilterMode : u16 {
    trilinear,
    point,
    bilinear,
    UNUSED_0,
    anisotropic_two_expensive,
    UNUSED_1,
    anisotropic_four_EXPENSIVE,
    lightprobe_texture_array,
    texture_array_quadlinear,
    texture_array_quadanisotropic_two,
};

enum SharpenMode : u16 {
    blur1,//2.00
    blur2,//1.75
    blur3,//1.50
    blur4,//1.25
    blur5,//1.00
    blur6,//0.75
    blur7,//0.50
    blur8,//0.25
    none,
    sharpen1,//0.25
    sharpen2,//0.50
    sharpen3,//0.75
    sharpen4//1.00
};

enum ExternMode : u16 {
    use_bitmap_as_normal,
    albedo_buffer,
    normal_buffer,
    dynamic_UI,
    depth_camera
};

enum Boolean : u32 {
    False,
    True
};

struct TgRf {
  type::Hex<u32> magic;
  u32 unk;
  u32 size;
 // if (size < 4) {
 //   padding [4];
 // }
  
  char name [size];
};

struct TgSt {
  type::Hex<u32> magic;
  type::Hex<u32> size;
  type::Hex<u32> data_size;
};

struct TgSt_size {
  type::Hex<u32> magic;
  type::Hex<u32> size;
  type::Hex<u32> data_size;
  char data [data_size];
};

struct TgIs {
  type::Hex<u32> magic;
  u32 unk;
  u32 size;
  //if (size < 4) {
  //  padding [4];
  //}
  
  char name [size];
};

struct TgBl {
  type::Hex<u32> magic;
  u32 unk;
  type::Hex<u32> size;
  type::Hex<u32> type; // count?
};

struct TgDa {
  type::Hex<u32> magic;
  u32 unk;
  u32 size;
  if (size < 4) {
    padding [4];
  }
};


struct MaterialParameter {
  padding[4];
  ParameterType parameterType;
   
    if (parameterType == ParameterType::bitmap) {
        padding[40];
        float Scale[2]; //U V, global in the mod tools just copies/overwrites U
        float Offset[2];
        padding [6];
        FilterMode Filter_Mode;
        WrapMode Wrap_Mode;
        WrapMode Wrap_Mode_U;
        WrapMode Wrap_Mode_V;
        SharpenMode Sharpen_Mode;
        ExternMode Extern_Mode;
        padding[86];
        
    }
   if (parameterType == ParameterType::color) {
        padding[24];
        float ARGB[4];
        padding[120];
    }
    if (parameterType == ParameterType::real) {
        padding[40];
        float real;
        padding[116];
    }    
    if (parameterType == ParameterType::boolean) {
        padding[56];
        Boolean boolean;
        padding[100];
    }    
    if (parameterType == ParameterType::int) {
        u32 parameterIndex;
        padding[68];
        u32 integer;
        float otherData[6];
        padding[600];
    }    
};

struct MaterialParameterData { //this is for strings only, links 1:1 with MaterialParameter
  TgSt_size tgst [[no_unique_address]]; 
  padding[12];
  TgIs tgis;
  TgRf tgrf;
  TgIs tgis2;
  padding [8];
  u32 paddingcount;
  padding[36];
  char data[paddingcount];
  
  
};

struct TagBlockMaterialParameters {
  type::Hex<u32> magic;
  type::Hex<u32> unk0;
  type::Hex<u32> size;
  type::Hex<u32> count;
  type::Hex<u32> unk2;
  
  MaterialParameter parameters [count];
  
  MaterialParameterData parameterdata [count];
};

struct BDat {
  type::Hex<u32> magic;
  u32 unk0;
  type::Hex<u32> size;
  
  TgBl tgbl;
  
  char unk1 [64];
  
  BlendModes Blend_Modes;
  padding[3];
  TransparentShadowPolicies Transparent_Shadow_Policies;
  
  TgSt tgst;
  TgRf tgrf;
  
  TagBlockMaterialParameters material_parameters;
  
};

struct Block {
  char unk0 [8];
  u32 size;
  char unk1 [size];
};

struct StringTable {
  char magic [4];
  u32 unk;
  u32 block_size;
  
  u64 beginBlock = $;
  NullString strings [while($ - beginBlock < block_size)];
};

struct Header {
  type::Hex<u32> stuff0 [24];
  
  type::Hex<u32> rel_offset_physics_material_type_string;
  
  type::Hex<u32> stuff1 [2];
  
  type::Hex<u32> rel_offset_tgst;
  
  type::Hex<u32> stuff2 [15];
  
  type::Hex<u32> rel_offset_bdat;
};

struct File {
  Header header;
  
  StringTable string_table;
  
  Block blocks [11];
  
  BDat bdat;
};



File file @ 0x00;