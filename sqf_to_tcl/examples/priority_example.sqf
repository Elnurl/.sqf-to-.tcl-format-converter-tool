;TOS_COM.sqf
;Command argument definitions (priority index, smaller = higher priority)
CM00001 1 IRU_Scale_Factor
CM00001 3 IRU_Drft_Bias
CM00001 2 RW_Speed

;Execute commands with values
C CM00001 0x1 0xcf
;This should output: CM00001 IRU_Scale_Factor=0x1 ; RW_Speed=0xcf ; IRU_Drft_Bias=0xcf
;But wait, we have 2 values and 3 arguments. Let me check the logic...

;Actually, with 2 values (0x1, 0xcf) and priorities 1, 2, 3:
;Value 0x1 -> priority 1 (IRU_Scale_Factor) - first value
;Value 0xcf -> priority 2 (RW_Speed) - second value
;No value for priority 3 (IRU_Drft_Bias) - not included in output

;So output should be: CM00001 IRU_Scale_Factor=0x1 ; RW_Speed=0xcf

;Test with 3 values
C CM00001 0x1 0xab 0xcf
;This should output: CM00001 IRU_Scale_Factor=0x1 ; RW_Speed=0xab ; IRU_Drft_Bias=0xcf

END

