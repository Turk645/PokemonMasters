bl_info = {
    "name": "Pokemon Masters Importer (.LMD)",
    "author": "Turk",
    "version": (1, 0, 5),
    "blender": (2, 80, 0),
    "location": "File > Import-Export",
    "description": "A tool designed to import LMD files from the mobile game Pokemon Masters",
    "warning": "",
    "category": "Import-Export",
}

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

class PokeMastImport(bpy.types.Operator, ImportHelper):
    bl_idname = "custom_import_scene.pokemonmasters"
    bl_label = "Import"
    bl_options = {'PRESET', 'UNDO'}
    filename_ext = ".lmd"
    filter_glob = StringProperty(
            default="*.lmd",
            options={'HIDDEN'},
            )
    filepath = StringProperty(subtype='FILE_PATH',)
    files = CollectionProperty(type=bpy.types.PropertyGroup)
    def draw(self, context):
        pass
    def execute(self, context):
        CurFile = open(self.filepath,"rb")
        CurCollection = bpy.data.collections.new("LMD Collection")#Make Collection per lmd loaded
        bpy.context.scene.collection.children.link(CurCollection)
        
        CurFile.seek(4)
        lmdCheck = int.from_bytes(CurFile.read(4),byteorder='little')
        if lmdCheck != 809782604:
            raise Exception("Invalid LMD file.")
        CurFile.seek(0x18)
        TypeTableOffset = int.from_bytes(CurFile.read(4),byteorder='little')
        tmpOffset = CurFile.seek(TypeTableOffset+0x1c)
        VersionPointer = int.from_bytes(CurFile.read(4),byteorder='little')
        CurFile.seek(tmpOffset+VersionPointer)
        StringLength = int.from_bytes(CurFile.read(4),byteorder='little')
        VersionString = CurFile.read(StringLength).decode('utf-8')
        print("LMD Version "+VersionString)
        CurFile.seek(tmpOffset+8)
        TypeCount = int.from_bytes(CurFile.read(4),byteorder='little')
        TypeTableStart = CurFile.tell()
        TypeTable = []
        ArmData = None
        for x in range(TypeCount):
            CurFile.seek(TypeTableStart+x*4)
            offset = int.from_bytes(CurFile.read(4),byteorder='little')
            CurFile.seek(offset-4,1)
            StringLength = int.from_bytes(CurFile.read(4),byteorder='little')
            TypeName = CurFile.read(StringLength).decode('utf-8')
            TypeTable.append(TypeName)
        for x in range(TypeCount):
            CurFile.seek(0x34+x*4)
            offset = CurFile.tell() + int.from_bytes(CurFile.read(4),byteorder='little')
            if TypeTable[x] == "mesh":
                parse_meshes(CurFile,offset,CurCollection,ArmData,self)
            elif TypeTable[x] == "bone":
                ArmData = parse_bones(CurFile,offset,CurCollection)
            elif TypeTable[x] == "material":
                parse_materials(CurFile,offset)
        
        
        
        CurFile.close()
        del CurFile
        return {'FINISHED'}

def parse_materials(CurFile,Start):
    print("Material chunk at "+hex(Start))
    return
    
def parse_bones(CurFile,Start,CurCollection):
    print("Bone chunk at "+hex(Start))
    CurFile.seek(Start+8)
    BoneCount = int.from_bytes(CurFile.read(4),byteorder='little')
    armature_data = bpy.data.armatures.new("Armature")
    armature_obj = bpy.data.objects.new("Armature", armature_data)
    CurCollection.objects.link(armature_obj)
    bpy.context.view_layer.objects.active = armature_obj
    utils_set_mode('EDIT')
    
    BoneTable = {}
    for x in range(BoneCount):
        CurFile.seek(Start+0xc+4*x)
        BoneOffset = CurFile.tell()+int.from_bytes(CurFile.read(4),byteorder='little')
        CurFile.seek(BoneOffset+4)
        BoneNameOffset = CurFile.tell() +int.from_bytes(CurFile.read(4),byteorder='little')
        BoneMatrix = mathutils.Matrix((struct.unpack('ffff', CurFile.read(4*4)),struct.unpack('ffff', CurFile.read(4*4)),struct.unpack('ffff', CurFile.read(4*4)),struct.unpack('ffff', CurFile.read(4*4))))
        BonePos = (BoneMatrix[3][0],BoneMatrix[3][1],BoneMatrix[3][2])
        BoneParentNameOffset = CurFile.tell() + int.from_bytes(CurFile.read(4),byteorder='little')
        #unknown bytes here
        CurFile.seek(BoneNameOffset)
        tmpLength = int.from_bytes(CurFile.read(4),byteorder='little')
        BoneName = CurFile.read(tmpLength).decode('utf-8')
        CurFile.seek(BoneParentNameOffset)
        tmpLength = int.from_bytes(CurFile.read(4),byteorder='little')
        BoneParentName = CurFile.read(tmpLength).decode('utf-8')
        
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
        if BoneParentName == "": continue
        edit_bone.parent = BoneTable[BoneParentName]["Bone"]
    utils_set_mode("POSE")
    for x in BoneTable:
        pbone = armature_obj.pose.bones[x]
        pbone.rotation_mode = 'XYZ'
        TempRot = BoneTable[x]["Matrix"].to_euler()
        pbone.rotation_euler = BoneTable[x]["Matrix"].inverted_safe().to_euler()
        pbone.location = BoneTable[x]["Position"]
        bpy.ops.pose.armature_apply()
    utils_set_mode("OBJECT")
    
    armature_obj.rotation_euler = (1.5707963705062866,0,0)

    return armature_obj
    
def parse_meshes(CurFile,Start,CurCollection,ArmData,self):
    CurFile.seek(Start+8)
    MeshCount = int.from_bytes(CurFile.read(4),byteorder='little')
    MeshCountOffset = CurFile.tell()
    for x in range(MeshCount):
        VertTable = []
        FaceTable = []
        NormalTable = []
        ColorData = []
        AlphaData = []
        UVTable = []
        WeightBoneTable = []
        VGData = []
        
        CurFile.seek(MeshCountOffset+x*4)
        MeshOffsetStart = CurFile.tell()+int.from_bytes(CurFile.read(4),byteorder='little')
        CurFile.seek(MeshOffsetStart+0x7)
        VertChunkSize = int.from_bytes(CurFile.read(1),byteorder='little')
        MeshNameOffset = CurFile.tell()+int.from_bytes(CurFile.read(4),byteorder='little')
        CurFile.seek(MeshNameOffset)
        StringLength = int.from_bytes(CurFile.read(4),byteorder='little')
        MeshName = CurFile.read(StringLength).decode('utf-8')
        CurFile.seek(MeshOffsetStart+0x14)
        MaterialTableOffset = CurFile.tell() + int.from_bytes(CurFile.read(4),byteorder='little')
        CurFile.seek(MaterialTableOffset+8)
        tmpLength = int.from_bytes(CurFile.read(4),byteorder='little')
        MaterialName = CurFile.read(tmpLength).decode('utf-8')
        MeshMat = create_material_info(self,MaterialName)
        #------------------Material Code here!!!
        #------------------Maybe put matrix info? Is it needed?
        #------------------Read Bone Weight Names
        CurFile.seek(MeshOffsetStart+0x58)
        BoneWeightNameOffset = CurFile.tell() + int.from_bytes(CurFile.read(4),byteorder='little')
        if (BoneWeightNameOffset - CurFile.tell()-4)>0:
            CurFile.seek(BoneWeightNameOffset)
            WeightBoneCount = int.from_bytes(CurFile.read(4),byteorder='little')
            for i in range(WeightBoneCount):
                CurFile.seek(BoneWeightNameOffset + i*4 + 4)
                WeightBoneNameOffset = CurFile.tell() + int.from_bytes(CurFile.read(4),byteorder='little')
                CurFile.seek(WeightBoneNameOffset)
                WeightBoneNameSize = int.from_bytes(CurFile.read(4),byteorder='little')
                WeightBoneName = CurFile.read(WeightBoneNameSize).decode('utf-8')
                WeightBoneTable.append(WeightBoneName)
        
        #------------------unknown bone pointer. Restartes bone position?
        CurFile.seek(MeshOffsetStart+0x78)
        FaceCount = int.from_bytes(CurFile.read(4),byteorder='little')
        FaceOffset = CurFile.tell() + int.from_bytes(CurFile.read(4),byteorder='little')
        VertLayoutOffset = CurFile.tell() + int.from_bytes(CurFile.read(4),byteorder='little')
        VertCount = int.from_bytes(CurFile.read(4),byteorder='little')
        VertOffset = CurFile.tell() + int.from_bytes(CurFile.read(4),byteorder='little')
        
        #read Vert Layout Info
        CurFile.seek(VertLayoutOffset)
        VertLayoutEntryCount = int.from_bytes(CurFile.read(4),byteorder='little')
        VertLayoutInfo = []
        for i in range(VertLayoutEntryCount):
            LayoutTypeEnum = int.from_bytes(CurFile.read(4),byteorder='little')
            LayoutTypeCount = int.from_bytes(CurFile.read(4),byteorder='little')
            LayoutTypeOffset = int.from_bytes(CurFile.read(4),byteorder='little')
            LayoutTypeModifier = int.from_bytes(CurFile.read(4),byteorder='little')
            VertLayoutInfo.append((LayoutTypeEnum,LayoutTypeCount,LayoutTypeOffset,LayoutTypeModifier))
        
        #Read Face Table
        CurFile.seek(FaceOffset)
        FaceChunkSize = int.from_bytes(CurFile.read(4),byteorder='little')
        FaceEntrySize = 2
        if FaceChunkSize > 65535:
            FaceEntrySize = 4
        elif FaceChunkSize < 256:
            FaceEntrySize = 1
        CurFile.seek(FaceEntrySize,1)
        if VertCount < 0x100:
            FSize = 1
        elif VertCount < 0x10000:
            FSize = 2
        else:
            FSize = 4
        for i in range(0,FaceCount,3):
            FaceTable.append((int.from_bytes(CurFile.read(FSize),byteorder='little'),int.from_bytes(CurFile.read(FSize),byteorder='little'),int.from_bytes(CurFile.read(FSize),byteorder='little')))
        #Read Vert Info
        CurFile.seek(VertOffset)
        VertChunkLength = int.from_bytes(CurFile.read(4),byteorder='little')
        tmpLength = 2
        if VertChunkLength > 65535:
            tmpLength = 4
        elif VertChunkLength < 256:
            tmpLength = 1
        VertDataStart = CurFile.seek(tmpLength,1)
        for i in range(VertCount):
            VertOffset = VertDataStart+i*VertChunkSize
            tmpOut = read_vertex_info(CurFile,VertLayoutInfo,VertOffset,i)
            VertTable.append(tmpOut[0])
            if tmpOut[1]: NormalTable.append(tmpOut[1])
            if tmpOut[2]: ColorData.append(tmpOut[2][0]);AlphaData.append(tmpOut[2][1])
            if tmpOut[3]: UVTable.append(tmpOut[3])
            if tmpOut[4] and tmpOut[5]:
                VGData.append((i,tmpOut[4],tmpOut[5]))
        
        
        #BuildMesh
        mesh1 = bpy.data.meshes.new("Mesh")
        mesh1.use_auto_smooth = True
        obj = bpy.data.objects.new(MeshName,mesh1)
        CurCollection.objects.link(obj)
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        mesh = bpy.context.object.data
        bm = bmesh.new()
        for v in VertTable:
            bm.verts.new((v[0],v[1],v[2]))
        list = [v for v in bm.verts]
        for f in FaceTable:
            try:
                bm.faces.new((list[f[0]],list[f[1]],list[f[2]]))
            except:
                continue
                
        bm.to_mesh(mesh)
        
        uv_layer = bm.loops.layers.uv.verify()
        Normals = []
        for f in bm.faces:
            f.smooth=True
            for l in f.loops:
                if NormalTable != []:
                    Normals.append(NormalTable[l.vert.index])
                luv = l[uv_layer]
                try:
                    luv.uv = UVTable[l.vert.index]
                except:
                    continue
        bm.to_mesh(mesh)
        
        if ColorData != []:
            color_layer = bm.loops.layers.color.new("Color")
            color_layerA = bm.loops.layers.color.new("Color_ALPHA")
            for f in bm.faces:
                for l in f.loops:
                    l[color_layer]= ColorData[l.vert.index]
                    l[color_layerA]= AlphaData[l.vert.index]
            bm.to_mesh(mesh)
            
        if WeightBoneTable != []:
            for x in VGData:
                for i in range(4):
                    if x[2][i] != 0:
                        if obj.vertex_groups.find(WeightBoneTable[x[1][i]]) == -1:
                            TempVG = obj.vertex_groups.new(name = WeightBoneTable[x[1][i]])
                        else:
                            TempVG = obj.vertex_groups[obj.vertex_groups.find(WeightBoneTable[x[1][i]])]
                        TempVG.add([x[0]],x[2][i],'ADD')
        
        bm.free()
        if NormalTable != []:
            mesh1.normals_split_custom_set(Normals)

        if len(obj.data.materials)>0:
            obj.data.materials[0]=MeshMat
        else:
            obj.data.materials.append(MeshMat)

        if ArmData:
            ArmMod = obj.modifiers.new("Armature","ARMATURE")
            ArmMod.object = ArmData
            obj.parent = ArmData
        else:
            obj.rotation_euler = (1.5707963705062866,0,0)
        
        
    return

def read_vertex_info(CurFile,LayoutTable,VertOffset,index):
    tmpVert = None
    tmpNorms = None
    tmpColors = None
    tmpUVs = None
    tmpBones = None
    tmpWeights = None
    for i in LayoutTable:
        CurFile.seek(VertOffset+i[2])
        if i[0] == 0: #Vertex Position
            tmpVert = struct.unpack('f'*i[1], CurFile.read(4*i[1]))
        elif i[0] == 1:#Normals
            tmpNorms = mathutils.Vector(ten_bit_normal_read(int.from_bytes(CurFile.read(4),byteorder='little'))).normalized()
        elif i[0] == 2:#VertexColors
            colorBytes = struct.unpack('4B', CurFile.read(4))
            color = (colorBytes[0]/255,colorBytes[1]/255,colorBytes[2]/255,colorBytes[3]/255)
            alpha = (colorBytes[3]/255,colorBytes[3]/255,colorBytes[3]/255,colorBytes[3]/255)
            tmpColors = [color,alpha]
            
        elif i[0] == 3:#UVs
            tmpUVs = (np.fromstring(CurFile.read(2), dtype='<f2'),1-np.fromstring(CurFile.read(2), dtype='<f2'))
        elif i[0] == 0xF:#Bone Link
            tmpBones = (int.from_bytes(CurFile.read(1),byteorder='little'),int.from_bytes(CurFile.read(1),byteorder='little'),int.from_bytes(CurFile.read(1),byteorder='little'),int.from_bytes(CurFile.read(1),byteorder='little'))
        elif i[0] == 0x10:#Bone Weights
            if i[3] == 0xB:
                tmpWeights = (int.from_bytes(CurFile.read(2),byteorder='little')/65535,int.from_bytes(CurFile.read(2),byteorder='little')/65535,int.from_bytes(CurFile.read(2),byteorder='little')/65535,int.from_bytes(CurFile.read(2),byteorder='little')/65535)
            else:
                tmpWeights = struct.unpack('ffff', CurFile.read(4*4))
    return tmpVert,tmpNorms,tmpColors,tmpUVs,tmpBones,tmpWeights

def sign_ten_bit(Input):
    if Input < 0x200: return Input
    else: return Input - 0x400
    end

def ten_bit_normal_read(RawNorm):
    Norm1 = sign_ten_bit(RawNorm & 0x3ff)/512
    Norm2 = sign_ten_bit((RawNorm >> 10) & 0x3ff)/512
    Norm3 = sign_ten_bit((RawNorm >> 20) & 0x3ff)/512
    return (Norm1,Norm2,Norm3)

def add_image_ref_to_mat(Mat,Path):
    Im = bpy.data.images.new(os.path.split(Path)[1],1,1)
    Im.source = 'FILE'
    Im.filepath = Path
    #Im.update()
    ImNode = Mat.node_tree.nodes.new("ShaderNodeTexImage")
    PrNode = Mat.node_tree.nodes['Principled BSDF']
    ImNode.image = Im
    
    Mat.node_tree.links.new(ImNode.outputs['Color'],PrNode.inputs['Base Color'])
    
    
    return

def create_material_info(self,matName):
    mat = bpy.data.materials.get(matName)
    if mat == None:
        mat = bpy.data.materials.new(name=matName)
        mat.use_nodes = True
    else:
        return mat
    mainDir = os.path.split(self.filepath)[0]
    matPath = os.path.join(mainDir,"Materials",matName+".material")
    if os.path.exists(matPath):
        MatFile = open(matPath,"rb")
        tmpRead = MatFile.read()
        texOffset = tmpRead.find(b"u_texture0")+11
        del tmpRead
        MatFile.seek(texOffset)
        texLength = int.from_bytes(MatFile.read(1),byteorder='little')
        texName = os.path.relpath(MatFile.read(texLength).decode('utf-8')).strip(".ktx")+".png"
        MatFile.close()
        del MatFile
        tmpOffset = texName.find("\\")+2
        tmpOffset = texName.find("\\",tmpOffset)
        tmpOffset = self.filepath.find(texName[:tmpOffset])
        texPath = os.path.join(self.filepath[:tmpOffset],texName)
        if os.path.exists(os.path.dirname(texPath)):
            add_image_ref_to_mat(mat,texPath)
    return mat

def utils_set_mode(mode):
    if bpy.ops.object.mode_set.poll():
        bpy.ops.object.mode_set(mode=mode, toggle=False)

def menu_func_import(self, context):
    self.layout.operator(PokeMastImport.bl_idname, text="Pokemon Masters (.lmd)")
        
def register():
    bpy.utils.register_class(PokeMastImport)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)
    
def unregister():
    bpy.utils.unregister_class(PokeMastImport)
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
        
if __name__ == "__main__":
    register()
