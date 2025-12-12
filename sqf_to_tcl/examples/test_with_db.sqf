;TOS_COM.sqf
;Test with database loaded - no need to define arguments in file
;Database should contain: CM00001 3 IRU_Drft_Bias, CM00001 4 IRU_Scale_Factor, CM00001 5 RW_Speed

;Execute commands with values
C CM00001 0x1 0xcf
;Should output: CM00001 IRU_Scale_Factor=0x1 ; RW_Speed=0xcf
;(Priority 3 is skipped if no value, priorities 4 and 5 get values)

C CM00001 0xab 0xcd 0xef
;Should output: CM00001 IRU_Drft_Bias=0xab ; IRU_Scale_Factor=0xcd ; RW_Speed=0xef

END

