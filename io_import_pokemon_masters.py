bl_info = {
    "name": "Import Pokemon Masters Models",
    "author": "Turk",
    "version": (1, 1, 0),
    "blender": (2, 79, 0),
    "location": "File > Import-Export",
    "description": "A tool designed to import LMD files from the mobile game Pokemon Masters",
    "warning": "",
    "wiki_url": "",
    "tracker_url": "",
    "category": "Import-Export"}

import bpy
import bmesh
import os
import io
import struct
import math
import mathutils
import numpy as np
from bpy.props import (BoolProperty,
                       FloatProperty,
                       StringProperty,
                       EnumProperty,
                       CollectionProperty
                       )
from bpy_extras.io_utils import ImportHelper
import fnmatch
import traceback

# To find a file in a path (including subfolders). Thanks Nadia Alramli
# for the answer from some corner in StackOverflow a decade ago
def find_file(pattern, path):
    result = []
    for root, dirs, files in os.walk(path):
        for name in files:
            if fnmatch.fnmatch(name, pattern):
                result.append(os.path.join(root, name))
    return result

class PokeMastImport(bpy.types.Operator, ImportHelper):
    bl_idname = "import_scene.pokemonmasters"
    bl_label = "Import"
    bl_options = {'PRESET', 'UNDO'}
    
    filename_ext = ".wismda"
    filter_glob = StringProperty(
            default="*.lmd",
            options={'HIDDEN'},
            )
 
    filepath = StringProperty(subtype='FILE_PATH',)
    version = EnumProperty(name="Version",items=(("1.0","1.0","1.0"),("1.2","1.2","1.2")),default="1.0")
    removedoubles = BoolProperty(name="Remove Doubles")

    files = CollectionProperty(type=bpy.types.PropertyGroup)
    def draw(self, context):
        layout = self.layout
        layout.separator()
        layout.prop(self,'version')
        #layout.separator()
        #layout.prop(self,'removedoubles')

    def execute(self, context):
        print("=====\nLoading file {}".format(self.filepath))

        CurFile = open(self.filepath,"rb")
        CurFile.seek(0x34)
        BoneDataOffset = CurFile.tell() + int.from_bytes(CurFile.read(4),byteorder='little')
        ArmatureObject = BuildSkeleton(CurFile,BoneDataOffset)
        CurFile.seek(0x38)
        MaterialDataOffset = CurFile.tell() + int.from_bytes(CurFile.read(4),byteorder='little')
        ParseMaterials(CurFile,MaterialDataOffset)
        
        CurFile.seek(0x48)
        MeshCount = int.from_bytes(CurFile.read(4),byteorder='little')
        MeshList = []
        for x in range(MeshCount):
            MeshList.append(CurFile.tell() + int.from_bytes(CurFile.read(4),byteorder='little'))
        CurMeshOffset = CurFile.tell()
        print("Loading meshes:")
        for x in MeshList:
            ReadMeshChunk(CurFile,x,ArmatureObject,self.version,self.removedoubles)

        CurFile.close()
        ArmatureObject.rotation_euler = (1.5707963705062866,0,0)
        return {'FINISHED'}
        
    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}


def ReadMeshChunk(CurFile,StartAddr,ArmatureObject,Version="1.0",RemoveDoubles=False):
    CurFile.seek(StartAddr+7)
    VertChunkSize = int.from_bytes(CurFile.read(1),byteorder='little')
    
    CurFile.seek(StartAddr+0x8)
    ModelNameArea = CurFile.tell() + int.from_bytes(CurFile.read(4),byteorder='little')
    CurFile.seek(ModelNameArea)
    ModelNameLength = int.from_bytes(CurFile.read(4),byteorder='little')
    ModelName = CurFile.read(ModelNameLength).decode('utf-8','replace')

    #Get Material Name
    CurFile.seek(StartAddr+0x14)
    MaterialNameOffset = CurFile.tell() + int.from_bytes(CurFile.read(4),byteorder='little')
    CurFile.seek(MaterialNameOffset+8)
    MaterialNameSize = int.from_bytes(CurFile.read(4),byteorder='little')
    MaterialNameText = CurFile.read(MaterialNameSize).decode('utf-8','replace')
    
    CurFile.seek(StartAddr+0x58)
    WeightBoneNameTableStart = CurFile.tell() + int.from_bytes(CurFile.read(4),byteorder='little')
    
    CurFile.seek(StartAddr+0x5C)
    WeightBoneTableStart = CurFile.tell() + int.from_bytes(CurFile.read(4),byteorder='little')
    
    CurFile.seek(StartAddr+0x78)
    FaceCount = int.from_bytes(CurFile.read(4),byteorder='little')
    CurFile.seek(StartAddr+0x84)
    VertCount = int.from_bytes(CurFile.read(4),byteorder='little')
    SizeTest = VertCount * VertChunkSize
    if SizeTest < 0x100:
        Size = 1
    elif SizeTest < 0x10000:
        Size = 2
    else:
        Size = 4
    CurFile.seek(8,1)
    VertSize = int.from_bytes(CurFile.read(Size),byteorder='little')
    VertOffset = CurFile.tell()
    
    #Read Vert Info Here
    VertTable = []
    UVTable = []
    VGData = []
    ColorData = []
    AlphaData = []
    bHasColor = False
    for x in range(VertCount):
        TempVert = struct.unpack('fff', CurFile.read(4*3))
        CurFile.seek(4,1)
        if (VertChunkSize >= 0x24) & (Version == "1.0"):
            bHasColor = True
            TempColor = struct.unpack('4B', CurFile.read(4))
            ColorData.append((TempColor[0]/255,TempColor[1]/255,TempColor[2]/255))
            AlphaData.append((TempColor[3]/255,TempColor[3]/255,TempColor[3]/255))
        TempUV = (np.fromstring(CurFile.read(2), dtype='<f2'),1-np.fromstring(CurFile.read(2), dtype='<f2'))
        if (VertChunkSize >= 0x24) & (Version == "1.0"):
            CurFile.seek(VertChunkSize - 0x24, 1)
        VGBone = (
            int.from_bytes(CurFile.read(1),byteorder='little'),
            int.from_bytes(CurFile.read(1),byteorder='little'),
            int.from_bytes(CurFile.read(1),byteorder='little'),
            int.from_bytes(CurFile.read(1),byteorder='little'))
        if Version == "1.0":
            VGWeight = (
                int.from_bytes(CurFile.read(2),byteorder='little')/65535,
                int.from_bytes(CurFile.read(2),byteorder='little')/65535,
                int.from_bytes(CurFile.read(2),byteorder='little')/65535,
                int.from_bytes(CurFile.read(2),byteorder='little')/65535)
        else:
            VGWeight = struct.unpack('ffff', CurFile.read(4*4))
        VGData.append((x,VGBone,VGWeight))
        VertTable.append(TempVert)
        UVTable.append(TempUV)
        
    if Size == 1: UnknownSize = 2
    else: UnknownSize = 4
    CurFile.seek(VertOffset+VertSize+Size+UnknownSize)
    UnknownCount = int.from_bytes(CurFile.read(4),byteorder='little')
    CurFile.seek(0x10*UnknownCount,1)
    SizeTest = int.from_bytes(CurFile.read(4),byteorder='little')
    if FaceCount < 0x100:
        Size = 1
    elif FaceCount < 0x10000:
        Size = 2
    else:
        Size = 4
    FaceSize = int.from_bytes(CurFile.read(Size),byteorder='little')
    if VertCount < 0x100:
        FSize = 1
    elif VertCount < 0x10000:
        FSize = 2
    else:
        FSize = 4
    #FaceCount = int(FaceSize/FSize)
    FaceOffset = CurFile.tell()
    
    #Read Faces
    FaceTable = []
    for x in range(0,FaceCount,3):
        FaceTable.append((int.from_bytes(CurFile.read(FSize),byteorder='little'),int.from_bytes(CurFile.read(FSize),byteorder='little'),int.from_bytes(CurFile.read(FSize),byteorder='little')))
        
    #GetWeight Paint Names
    WeightBoneTable = []
    CurFile.seek(WeightBoneNameTableStart)
    WeightBoneCount = int.from_bytes(CurFile.read(4),byteorder='little')

    for x in range(WeightBoneCount):
        CurFile.seek(WeightBoneNameTableStart + x*4 + 4)
        WeightBoneNameOffset = CurFile.tell() + int.from_bytes(CurFile.read(4),byteorder='little')
        CurFile.seek(WeightBoneNameOffset)
        WeightBoneNameSize = int.from_bytes(CurFile.read(4),byteorder='little')
        WeightBoneName = CurFile.read(WeightBoneNameSize).decode('utf-8','replace')
        WeightBoneTable.append(WeightBoneName)
        print('{}: {}'.format(WeightBoneName,WeightBoneNameOffset))
    
    #Build Mesh
    
    mesh1 = bpy.data.meshes.new("mesh")
    mesh1.use_auto_smooth = True
    obj = bpy.data.objects.new(ModelName, mesh1)
    scene = bpy.context.scene
    scene.objects.link(obj)
    scene.objects.active = obj
    obj.select = True 
    mesh = bpy.context.object.data
    bm = bmesh.new()
    for v in VertTable:
        bm.verts.new((v[0],v[1],v[2]))
    vlist = [v for v in bm.verts]
    for f in FaceTable:
        try:
            bm.faces.new((vlist[f[0]],vlist[f[1]],vlist[f[2]]))
        except:
            continue
    print('- {}: {} - {}'.format(ModelName,MaterialNameText,len(vlist)))

    bm.to_mesh(mesh)

    uv_layer = bm.loops.layers.uv.verify()
    bm.faces.layers.tex.verify()
    for f in bm.faces:
        f.smooth=True
        for l in f.loops:
            luv = l[uv_layer]
            try:
                luv.uv = UVTable[l.vert.index]
            except:
                continue
    bm.to_mesh(mesh)
    mesh.auto_smooth_angle = 1.2
    """if RemoveDoubles:
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.00001)
        bm.to_mesh(mesh)
        mesh.validate(verbose=True)
        mesh.update()"""

    if bHasColor:
        color_layer = bm.loops.layers.color.new("Color")
        color_layerA = bm.loops.layers.color.new("Color_ALPHA")
        for f in bm.faces:
            for l in f.loops:
                l[color_layer]= ColorData[l.vert.index]
                l[color_layerA]= AlphaData[l.vert.index]
        bm.to_mesh(mesh)

    bm.free()

    #try vertex group creation
    for x in VGData:
        for i in range(4):
            if x[2][i] != 0:
                try:
                    if obj.vertex_groups.find(WeightBoneTable[x[1][i]]) == -1:
                        TempVG = obj.vertex_groups.new(WeightBoneTable[x[1][i]])
                    else:
                        TempVG = obj.vertex_groups[obj.vertex_groups.find(WeightBoneTable[x[1][i]])]
                    TempVG.add([x[0]],x[2][i],'ADD')
                except Exception as e:
                    print (" WEIGHT FAIL")

    #add materials
    if obj.data.materials:
        obj.data.materials[0]=bpy.data.materials.get(MaterialNameText)
    else:
        obj.data.materials.append(bpy.data.materials.get(MaterialNameText))
    
    #add armature to mesh
    Arm = obj.modifiers.new("Armature","ARMATURE")
    Arm.object = ArmatureObject
    obj.parent = ArmatureObject
    
    return

def BuildSkeleton(CurFile,DataStart):
    CurFile.seek(DataStart+8)
    BoneCount = int.from_bytes(CurFile.read(4),byteorder='little')
    BoneOffsetTable = []
    for x in range(BoneCount):
        BoneOffsetTable.append(CurFile.tell()+int.from_bytes(CurFile.read(4),byteorder='little'))

    name = os.path.split(CurFile.name)[-1]
    armature_data = bpy.data.armatures.new(name)
    armature_obj = bpy.data.objects.new(name, armature_data)
    bpy.context.scene.objects.link(armature_obj)
    select_all(False)
    armature_obj.select = True
    bpy.context.scene.objects.active = armature_obj
    utils_set_mode('EDIT')
    
    BoneTable = {}
    for x in BoneOffsetTable:
        CurFile.seek(x)
        Magic = int.from_bytes(CurFile.read(4),byteorder='little')
        CurFile.seek(x+4)
        NameOffset = CurFile.tell() + int.from_bytes(CurFile.read(4),byteorder='little')
        CurFile.seek(NameOffset)
        BoneNameLength = int.from_bytes(CurFile.read(4),byteorder='little')
        BoneName = CurFile.read(BoneNameLength).decode('utf-8','replace')
        CurFile.seek(x+8)
        BoneMatrix = mathutils.Matrix((struct.unpack('ffff', CurFile.read(4*4)),struct.unpack('ffff', CurFile.read(4*4)),struct.unpack('ffff', CurFile.read(4*4)),struct.unpack('ffff', CurFile.read(4*4))))
        CurFile.seek(x+0x38)
        BonePos = struct.unpack('fff', CurFile.read(4*3))
        CurFile.seek(x+0x48)
        BoneParentOffset = CurFile.tell() + int.from_bytes(CurFile.read(4),byteorder='little')
        CurFile.seek(BoneParentOffset)
        BoneParentNameLength = int.from_bytes(CurFile.read(4),byteorder='little')
        BoneParentName = CurFile.read(BoneParentNameLength).decode('utf-8','replace')
        
        edit_bone = armature_obj.data.edit_bones.new(BoneName)
        edit_bone.use_connect = False
        edit_bone.use_inherit_rotation = True
        edit_bone.use_inherit_scale = True
        edit_bone.use_local_location = True
        edit_bone.head = (0,0,0)
        edit_bone.tail = (0,0.05,0)
        armature_obj.data.edit_bones.active = edit_bone
        BoneTable[BoneName] = {}
        BoneTable[BoneName]["Bone"] = edit_bone
        BoneTable[BoneName]["Parent"] = BoneParentName
        BoneTable[BoneName]["Position"] = BonePos
        BoneTable[BoneName]["Matrix"] = BoneMatrix
        BoneTable[BoneName]["Name"] = BoneName
        if Magic < 0x5000: continue
        edit_bone.parent = BoneTable[BoneParentName]["Bone"]
        #print(BoneName)
    
    bpy.context.scene.objects.active = armature_obj
    utils_set_mode("POSE")
    for x in BoneTable:
        pbone = armature_obj.pose.bones[x]
        pbone.rotation_mode = 'XYZ'
        TempRot = BoneTable[x]["Matrix"].to_euler()
        pbone.rotation_euler = (-TempRot[0],-TempRot[1],-TempRot[2])
        pbone.location = BoneTable[x]["Position"]
        bpy.ops.pose.armature_apply()
    
    utils_set_mode('OBJECT')
    return armature_obj

def ParseMaterials(CurFile,DataStart):
    MatTable = []
    CurFile.seek(DataStart+4)
    MaterialNameOffset = CurFile.tell() + int.from_bytes(CurFile.read(4),byteorder='little')
    CurFile.seek(DataStart+12)
    TextureCount = int.from_bytes(CurFile.read(4),byteorder='little')
    TextureOffSetTable = []
    for x in range(TextureCount):
        TextureOffSetTable.append(CurFile.tell() + int.from_bytes(CurFile.read(4), byteorder='little'))
    Textures = {}
    print("Loading {} texture{}:".format(TextureCount,'' if TextureCount == 1 else 's'))
    for x in TextureOffSetTable:
        CurFile.seek(x+4)
        TexFileRefOffset = CurFile.tell() + int.from_bytes(CurFile.read(4),byteorder='little')
        TexFileNameOffset = CurFile.tell() + int.from_bytes(CurFile.read(4),byteorder='little')
        TexFileMapOffset = CurFile.tell() + int.from_bytes(CurFile.read(4),byteorder='little')
        CurFile.seek(TexFileNameOffset)
        TexFileNameSize = int.from_bytes(CurFile.read(4),byteorder='little')
        TexFileName = CurFile.read(TexFileNameSize).decode('utf-8','replace')

        CurFile.seek(TexFileRefOffset)
        TexFileRefSize = int.from_bytes(CurFile.read(4),byteorder='little')
        TexFileRef = CurFile.read(TexFileRefSize).decode('utf-8','replace')

        CurFile.seek(TexFileMapOffset)
        TexFileMapSize = int.from_bytes(CurFile.read(4),byteorder='little')
        TexFileMap = CurFile.read(TexFileMapSize).decode('utf-8','replace')
        Textures.update({TexFileRef:TexFileName})
        tex = bpy.data.textures.get(TexFileName)
        if not tex:
            tex = bpy.data.textures.new(name=TexFileName,type='IMAGE')
            try:
                filepath = os.path.split(os.path.realpath(CurFile.name))
                files = find_file(TexFileName, filepath[0])
                # Try finding the file by brute force
                if not files:
                    files = find_file(TexFileName.replace(".tga",".ktx.tga"), filepath[0])
                if not files:
                    files = find_file(TexFileName.replace(".tga",".png"), filepath[0])
                if not files:
                    files = find_file(TexFileName.replace(".tga", ".ktx.png"), filepath[0])
                if not files:
                    files = find_file(TexFileName.replace(".tga", "*.png"), filepath[0])
                if files:
                    bpy.ops.image.open(filepath=files[0])
                    filename = os.path.split(files[0])[-1]
                    tex.image = bpy.data.images.get(filename)
            except:
                print(traceback.format_exc())
        print("- {}: {} / {}".format(TexFileRef,TexFileName,TexFileMap))

    CurFile.seek(MaterialNameOffset)
    MaterialCount = int.from_bytes(CurFile.read(4),byteorder='little')
    print("Loading {} material{}:".format(MaterialCount,'' if MaterialCount == 1 else 's'))
    MatOffsetTable = []
    for x in range(MaterialCount):
        MatOffsetTable.append(CurFile.tell() + int.from_bytes(CurFile.read(4),byteorder='little'))
    for x in MatOffsetTable:
        CurFile.seek(x+4)
        MaterialNameTextOffset = CurFile.tell() + int.from_bytes(CurFile.read(4),byteorder='little')
        CurFile.seek(MaterialNameTextOffset)
        MaterialNameTextSize = int.from_bytes(CurFile.read(4),byteorder='little')
        MaterialNameText = CurFile.read(MaterialNameTextSize).decode('utf-8','replace')

        CurFile.seek(x + 0x38)
        flag = int.from_bytes(CurFile.read(4),byteorder='little')
        if flag == 0x40000000:
            CurFile.seek(x + 0x44)
        else:
            CurFile.seek(x + 0x40)
        TexSlotCount = int.from_bytes(CurFile.read(4),byteorder='little')
        TexSlotsOffset = []
        TexSlots = []
        print("- {}".format(MaterialNameText))

        for y in range(TexSlotCount):
            TexSlotsOffset.append(CurFile.tell() + int.from_bytes(CurFile.read(4),byteorder='little'))
        for texslot in TexSlotsOffset:
            CurFile.seek(texslot)
            MaterialFileReferenceSize = int.from_bytes(CurFile.read(4),byteorder='little')
            MaterialFileReferenceName = CurFile.read(MaterialFileReferenceSize).decode('utf-8','replace')
            print('- Texture slot [{}]'.format(MaterialFileReferenceName))
            TexSlots.append(Textures.get(MaterialFileReferenceName))

        mat = bpy.data.materials.get(MaterialNameText)
        if mat == None:
            mat = bpy.data.materials.new(name=MaterialNameText)
            mat.use_transparency=True
            mat.alpha = 0.0
            for texture in TexSlots:
                tex = bpy.data.textures.get(texture)
                if tex:
                    slot = mat.texture_slots.add()
                    slot.use_map_alpha = True
                    slot.texture = tex
        MatTable.append(mat)
    return MatTable
    
def select_all(select):
    if select:
        actionString = 'SELECT'
    else:
        actionString = 'DESELECT'

    if bpy.ops.object.select_all.poll():
        bpy.ops.object.select_all(action=actionString)

    if bpy.ops.mesh.select_all.poll():
        bpy.ops.mesh.select_all(action=actionString)

    if bpy.ops.pose.select_all.poll():
        bpy.ops.pose.select_all(action=actionString)

def utils_set_mode(mode):
    if bpy.ops.object.mode_set.poll():
        bpy.ops.object.mode_set(mode=mode, toggle=False)

def menu_func_import(self, context):
    self.layout.operator(PokeMastImport.bl_idname, text="Pokemon Masters (.lmd)")

def register():
    bpy.utils.register_class(PokeMastImport)
    bpy.types.INFO_MT_file_import.append(menu_func_import)


def unregister():
    bpy.utils.unregister_class(PokeMastImport)
    bpy.types.INFO_MT_file_import.remove(menu_func_import)
       
if __name__ == "__main__":
    register()
