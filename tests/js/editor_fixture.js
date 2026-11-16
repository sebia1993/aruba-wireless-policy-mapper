'use strict';
module.exports = function fixture() {
  const at = '2026-11-16T01:00:00Z';
  const record = {text:'기존 설명',status:'reviewed',updatedAt:at,confirmedAt:at,reasons:[],source:null};
  return {
    format:'aruba-policy-annotations',schemaVersion:1,projectId:'project-a',revision:0,
    createdAt:at,updatedAt:at,snapshot:{id:'snapshot-a',collectedAt:at,
      controllers:[{id:'controller-a',name:'WLC-A',host:'192.0.2.1',port:22,scope:'effective',identityKnown:true,coverage:'completed',failedCommands:[]}],
      roles:[{id:'role-a',controllerId:'controller-a',name:'EMPLOYEE',ssids:['corp'],roleTypes:['default'],aclOrder:['EMPLOYEE'],bindingRaw:['session-acl EMPLOYEE'],contextComplete:true,observedUsers:2}],
      rules:[{id:'rule-a',controllerId:'controller-a',roleId:'role-a',acl:'EMPLOYEE',sequence:'1',ordinal:1,raw:'any any any permit',source:'any',destination:'any',service:'any',action:'permit',sourceInterpretation:'',destinationInterpretation:''}],
      aliases:[],localNetworks:[],issues:[]},
    annotations:{roles:{},rules:{'rule-a':record}},unresolvedAnnotations:[],changes:[],importHistory:[]
  };
};
