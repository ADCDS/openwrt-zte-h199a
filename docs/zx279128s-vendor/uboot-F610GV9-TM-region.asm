
region.bin:     file format binary


Disassembly of section .data:

47f30000 <.data>:
47f30000:	e3a0002b 	mov	r0, #43	@ 0x2b
47f30004:	ebfffee9 	bl	0x47f2fbb0
47f30008:	e3a0002f 	mov	r0, #47	@ 0x2f
47f3000c:	ebfffee7 	bl	0x47f2fbb0
47f30010:	e3a0002e 	mov	r0, #46	@ 0x2e
47f30014:	ebfffee5 	bl	0x47f2fbb0
47f30018:	e3a0002d 	mov	r0, #45	@ 0x2d
47f3001c:	ebfffee3 	bl	0x47f2fbb0
47f30020:	e3a00005 	mov	r0, #5
47f30024:	ebfffec5 	bl	0x47f2fb40
47f30028:	e1a05000 	mov	r5, r0
47f3002c:	e3a0000f 	mov	r0, #15
47f30030:	ebfffec2 	bl	0x47f2fb40
47f30034:	e1a04000 	mov	r4, r0
47f30038:	e3a0003e 	mov	r0, #62	@ 0x3e
47f3003c:	ebfffebf 	bl	0x47f2fb40
47f30040:	e1a00100 	lsl	r0, r0, #2
47f30044:	e1804084 	orr	r4, r0, r4, lsl #1
47f30048:	e3a0003d 	mov	r0, #61	@ 0x3d
47f3004c:	ebfffebb 	bl	0x47f2fb40
47f30050:	e1844005 	orr	r4, r4, r5
47f30054:	e6ef4074 	uxtb	r4, r4
47f30058:	e1840180 	orr	r0, r4, r0, lsl #3
47f3005c:	e6ef4070 	uxtb	r4, r0
47f30060:	e3a0002b 	mov	r0, #43	@ 0x2b
47f30064:	ebfffeb5 	bl	0x47f2fb40
47f30068:	e1840200 	orr	r0, r4, r0, lsl #4
47f3006c:	e6ef4070 	uxtb	r4, r0
47f30070:	e3a0002f 	mov	r0, #47	@ 0x2f
47f30074:	ebfffeb1 	bl	0x47f2fb40
47f30078:	e1840280 	orr	r0, r4, r0, lsl #5
47f3007c:	e6ef4070 	uxtb	r4, r0
47f30080:	e3a0002e 	mov	r0, #46	@ 0x2e
47f30084:	ebfffead 	bl	0x47f2fb40
47f30088:	e1840300 	orr	r0, r4, r0, lsl #6
47f3008c:	e6ef4070 	uxtb	r4, r0
47f30090:	e3a0002d 	mov	r0, #45	@ 0x2d
47f30094:	ebfffea9 	bl	0x47f2fb40
47f30098:	e1840380 	orr	r0, r4, r0, lsl #7
47f3009c:	e6ef4070 	uxtb	r4, r0
47f300a0:	e59f0028 	ldr	r0, [pc, #40]	@ 0x47f300d0
47f300a4:	e1a01004 	mov	r1, r4
47f300a8:	ebff692a 	bl	0x47f0a558
47f300ac:	e35400b1 	cmp	r4, #177	@ 0xb1
47f300b0:	9a000004 	bls	0x47f300c8
47f300b4:	e59f0018 	ldr	r0, [pc, #24]	@ 0x47f300d4
47f300b8:	e3002425 	movw	r2, #1061	@ 0x425
47f300bc:	e59f1014 	ldr	r1, [pc, #20]	@ 0x47f300d8
47f300c0:	e3a04000 	mov	r4, #0
47f300c4:	ebff6923 	bl	0x47f0a558
47f300c8:	e1a00004 	mov	r0, r4
47f300cc:	e8bd8038 	pop	{r3, r4, r5, pc}
47f300d0:	47f4409e 			@ <UNDEFINED> instruction: 0x47f4409e
47f300d4:	47f44060 	ldrbmi	r4, [r4, r0, rrx]!
47f300d8:	47f3a580 	ldrbmi	r10, [r3, r0, lsl #11]!
47f300dc:	e24dd008 	sub	sp, sp, #8
47f300e0:	e3a03000 	mov	r3, #0
47f300e4:	e58d3004 	str	r3, [sp, #4]
47f300e8:	e59f305c 	ldr	r3, [pc, #92]	@ 0x47f3014c
47f300ec:	e5932000 	ldr	r2, [r3]
47f300f0:	e58d2004 	str	r2, [sp, #4]
47f300f4:	e59d2004 	ldr	r2, [sp, #4]
47f300f8:	e3822b03 	orr	r2, r2, #3072	@ 0xc00
47f300fc:	e58d2004 	str	r2, [sp, #4]
47f30100:	e59d2004 	ldr	r2, [sp, #4]
47f30104:	e5832000 	str	r2, [r3]
47f30108:	e5932004 	ldr	r2, [r3, #4]
47f3010c:	e58d2004 	str	r2, [sp, #4]
47f30110:	e59d2004 	ldr	r2, [sp, #4]
47f30114:	e38220c0 	orr	r2, r2, #192	@ 0xc0
47f30118:	e58d2004 	str	r2, [sp, #4]
47f3011c:	e59d2004 	ldr	r2, [sp, #4]
47f30120:	e5832004 	str	r2, [r3, #4]
47f30124:	e593200c 	ldr	r2, [r3, #12]
47f30128:	e58d2004 	str	r2, [sp, #4]
47f3012c:	e59d2004 	ldr	r2, [sp, #4]
47f30130:	e3822706 	orr	r2, r2, #1572864	@ 0x180000
47f30134:	e3822d3a 	orr	r2, r2, #3712	@ 0xe80
47f30138:	e58d2004 	str	r2, [sp, #4]
47f3013c:	e59d2004 	ldr	r2, [sp, #4]
47f30140:	e583200c 	str	r2, [r3, #12]
47f30144:	e28dd008 	add	sp, sp, #8
47f30148:	e12fff1e 	bx	lr
47f3014c:	94200000 	strtls	r0, [r0], #-0
47f30150:	e92d4038 	push	{r3, r4, r5, lr}
47f30154:	e3a00003 	mov	r0, #3
47f30158:	ebfffe94 	bl	0x47f2fbb0
47f3015c:	e3a0000f 	mov	r0, #15
47f30160:	ebfffe92 	bl	0x47f2fbb0
47f30164:	e3a0003e 	mov	r0, #62	@ 0x3e
47f30168:	ebfffe90 	bl	0x47f2fbb0
47f3016c:	e3a0003d 	mov	r0, #61	@ 0x3d
47f30170:	ebfffe8e 	bl	0x47f2fbb0
47f30174:	e3a0002f 	mov	r0, #47	@ 0x2f
47f30178:	ebfffe8c 	bl	0x47f2fbb0
47f3017c:	e3a0002e 	mov	r0, #46	@ 0x2e
47f30180:	ebfffe8a 	bl	0x47f2fbb0
47f30184:	e3a0002d 	mov	r0, #45	@ 0x2d
47f30188:	ebfffe88 	bl	0x47f2fbb0
47f3018c:	e3a0002b 	mov	r0, #43	@ 0x2b
47f30190:	ebfffe86 	bl	0x47f2fbb0
47f30194:	e3a00003 	mov	r0, #3
47f30198:	ebfffe68 	bl	0x47f2fb40
47f3019c:	e1a05000 	mov	r5, r0
47f301a0:	e3a0000f 	mov	r0, #15
47f301a4:	ebfffe65 	bl	0x47f2fb40
47f301a8:	e1a04000 	mov	r4, r0
47f301ac:	e3a0003e 	mov	r0, #62	@ 0x3e
47f301b0:	ebfffe62 	bl	0x47f2fb40
47f301b4:	e1a00100 	lsl	r0, r0, #2
47f301b8:	e1804084 	orr	r4, r0, r4, lsl #1
47f301bc:	e3a0003d 	mov	r0, #61	@ 0x3d
47f301c0:	ebfffe5e 	bl	0x47f2fb40
47f301c4:	e1844005 	orr	r4, r4, r5
47f301c8:	e6ef4074 	uxtb	r4, r4
47f301cc:	e1840180 	orr	r0, r4, r0, lsl #3
47f301d0:	e6ef4070 	uxtb	r4, r0
47f301d4:	e3a0002f 	mov	r0, #47	@ 0x2f
47f301d8:	ebfffe58 	bl	0x47f2fb40
47f301dc:	e1840200 	orr	r0, r4, r0, lsl #4
47f301e0:	e6ef4070 	uxtb	r4, r0
47f301e4:	e3a0002e 	mov	r0, #46	@ 0x2e
47f301e8:	ebfffe54 	bl	0x47f2fb40
47f301ec:	e1840280 	orr	r0, r4, r0, lsl #5
47f301f0:	e6ef4070 	uxtb	r4, r0
47f301f4:	e3a0002d 	mov	r0, #45	@ 0x2d
47f301f8:	ebfffe50 	bl	0x47f2fb40
47f301fc:	e1840300 	orr	r0, r4, r0, lsl #6
47f30200:	e6ef4070 	uxtb	r4, r0
47f30204:	e3a0002b 	mov	r0, #43	@ 0x2b
47f30208:	ebfffe4c 	bl	0x47f2fb40
47f3020c:	e1840380 	orr	r0, r4, r0, lsl #7
47f30210:	e6ef4070 	uxtb	r4, r0
47f30214:	e59f0028 	ldr	r0, [pc, #40]	@ 0x47f30244
47f30218:	e1a01004 	mov	r1, r4
47f3021c:	ebff68cd 	bl	0x47f0a558
47f30220:	e3540094 	cmp	r4, #148	@ 0x94
47f30224:	9a000004 	bls	0x47f3023c
47f30228:	e59f0018 	ldr	r0, [pc, #24]	@ 0x47f30248
47f3022c:	e3a0204f 	mov	r2, #79	@ 0x4f
47f30230:	e59f1014 	ldr	r1, [pc, #20]	@ 0x47f3024c
47f30234:	e3a04000 	mov	r4, #0
47f30238:	ebff68c6 	bl	0x47f0a558
47f3023c:	e1a00004 	mov	r0, r4
47f30240:	e8bd8038 	pop	{r3, r4, r5, pc}
47f30244:	47f440b5 			@ <UNDEFINED> instruction: 0x47f440b5
47f30248:	47f44060 	ldrbmi	r4, [r4, r0, rrx]!
47f3024c:	47f3a591 			@ <UNDEFINED> instruction: 0x47f3a591
47f30250:	e92d401f 	push	{r0, r1, r2, r3, r4, lr}
47f30254:	e3a03000 	mov	r3, #0
47f30258:	e59f0094 	ldr	r0, [pc, #148]	@ 0x47f302f4
47f3025c:	e58d300c 	str	r3, [sp, #12]
47f30260:	e5903000 	ldr	r3, [r0]
47f30264:	e58d300c 	str	r3, [sp, #12]
47f30268:	e59d300c 	ldr	r3, [sp, #12]
47f3026c:	e38330c0 	orr	r3, r3, #192	@ 0xc0
47f30270:	e58d300c 	str	r3, [sp, #12]
47f30274:	e59d300c 	ldr	r3, [sp, #12]
47f30278:	e5803000 	str	r3, [r0]
47f3027c:	e5903004 	ldr	r3, [r0, #4]
47f30280:	e58d300c 	str	r3, [sp, #12]
47f30284:	e59d300c 	ldr	r3, [sp, #12]
47f30288:	e3833003 	orr	r3, r3, #3
47f3028c:	e58d300c 	str	r3, [sp, #12]
47f30290:	e59d300c 	ldr	r3, [sp, #12]
47f30294:	e5803004 	str	r3, [r0, #4]
47f30298:	e590300c 	ldr	r3, [r0, #12]
47f3029c:	e58d300c 	str	r3, [sp, #12]
47f302a0:	e59d300c 	ldr	r3, [sp, #12]
47f302a4:	e3833b03 	orr	r3, r3, #3072	@ 0xc00
47f302a8:	e58d300c 	str	r3, [sp, #12]
47f302ac:	e59d300c 	ldr	r3, [sp, #12]
47f302b0:	e580300c 	str	r3, [r0, #12]
47f302b4:	e5903008 	ldr	r3, [r0, #8]
47f302b8:	e58d300c 	str	r3, [sp, #12]
47f302bc:	e59d300c 	ldr	r3, [sp, #12]
47f302c0:	e383361d 	orr	r3, r3, #30408704	@ 0x1d00000
47f302c4:	e58d300c 	str	r3, [sp, #12]
47f302c8:	e59d300c 	ldr	r3, [sp, #12]
47f302cc:	e5803008 	str	r3, [r0, #8]
47f302d0:	e5901000 	ldr	r1, [r0]
47f302d4:	e5902004 	ldr	r2, [r0, #4]
47f302d8:	e5903008 	ldr	r3, [r0, #8]
47f302dc:	e590000c 	ldr	r0, [r0, #12]
47f302e0:	e58d0000 	str	r0, [sp]
47f302e4:	e59f000c 	ldr	r0, [pc, #12]	@ 0x47f302f8
47f302e8:	ebff689a 	bl	0x47f0a558
47f302ec:	e28dd014 	add	sp, sp, #20
47f302f0:	e49df004 	pop	{pc}		@ (ldr pc, [sp], #4)
47f302f4:	94200000 	strtls	r0, [r0], #-0
47f302f8:	47f440cc 	ldrbmi	r4, [r4, r12, asr #1]!
47f302fc:	e59f3004 	ldr	r3, [pc, #4]	@ 0x47f30308
47f30300:	e5d30000 	ldrb	r0, [r3]
47f30304:	e12fff1e 	bx	lr
47f30308:	47f6218c 	ldrbmi	r2, [r6, r12, lsl #3]!
47f3030c:	e92d4073 	push	{r0, r1, r4, r5, r6, lr}
47f30310:	e3a04000 	mov	r4, #0
47f30314:	e59f50b8 	ldr	r5, [pc, #184]	@ 0x47f303d4
47f30318:	e59f00b8 	ldr	r0, [pc, #184]	@ 0x47f303d8
47f3031c:	e5953004 	ldr	r3, [r5, #4]
47f30320:	e2831008 	add	r1, r3, #8
47f30324:	e891000e 	ldm	r1, {r1, r2, r3}
47f30328:	ebff688a 	bl	0x47f0a558
47f3032c:	e5953004 	ldr	r3, [r5, #4]
47f30330:	e1a01004 	mov	r1, r4
47f30334:	e59f00a0 	ldr	r0, [pc, #160]	@ 0x47f303dc
47f30338:	e0833104 	add	r3, r3, r4, lsl #2
47f3033c:	e2844001 	add	r4, r4, #1
47f30340:	e59f608c 	ldr	r6, [pc, #140]	@ 0x47f303d4
47f30344:	e5932018 	ldr	r2, [r3, #24]
47f30348:	ebff6882 	bl	0x47f0a558
47f3034c:	e3540004 	cmp	r4, #4
47f30350:	1afffff5 	bne	0x47f3032c
47f30354:	e5963004 	ldr	r3, [r6, #4]
47f30358:	e3a04000 	mov	r4, #0
47f3035c:	e59f007c 	ldr	r0, [pc, #124]	@ 0x47f303e0
47f30360:	e5931014 	ldr	r1, [r3, #20]
47f30364:	ebff687b 	bl	0x47f0a558
47f30368:	e5963004 	ldr	r3, [r6, #4]
47f3036c:	e59f0070 	ldr	r0, [pc, #112]	@ 0x47f303e4
47f30370:	e3a06014 	mov	r6, #20
47f30374:	e593102c 	ldr	r1, [r3, #44]	@ 0x2c
47f30378:	ebff6876 	bl	0x47f0a558
47f3037c:	e5953004 	ldr	r3, [r5, #4]
47f30380:	e593202c 	ldr	r2, [r3, #44]	@ 0x2c
47f30384:	e1540002 	cmp	r4, r2
47f30388:	2a00000f 	bcs	0x47f303cc
47f3038c:	e00c0496 	mul	r12, r6, r4
47f30390:	e593e028 	ldr	lr, [r3, #40]	@ 0x28
47f30394:	e08e200c 	add	r2, lr, r12
47f30398:	e592100c 	ldr	r1, [r2, #12]
47f3039c:	e3510000 	cmp	r1, #0
47f303a0:	0a000007 	beq	0x47f303c4
47f303a4:	e5d23004 	ldrb	r3, [r2, #4]
47f303a8:	e5922008 	ldr	r2, [r2, #8]
47f303ac:	e59f0034 	ldr	r0, [pc, #52]	@ 0x47f303e8
47f303b0:	e58d1004 	str	r1, [sp, #4]
47f303b4:	e1a01004 	mov	r1, r4
47f303b8:	e58d2000 	str	r2, [sp]
47f303bc:	e79e200c 	ldr	r2, [lr, r12]
47f303c0:	ebff6864 	bl	0x47f0a558
47f303c4:	e2844001 	add	r4, r4, #1
47f303c8:	eaffffeb 	b	0x47f3037c
47f303cc:	e28dd008 	add	sp, sp, #8
47f303d0:	e8bd8070 	pop	{r4, r5, r6, pc}
47f303d4:	47f6218c 	ldrbmi	r2, [r6, r12, lsl #3]!
47f303d8:	47f440e9 	ldrbmi	r4, [r4, r9, ror #1]!
47f303dc:	47f44114 			@ <UNDEFINED> instruction: 0x47f44114
47f303e0:	47f44120 	ldrbmi	r4, [r4, r0, lsr #2]!
47f303e4:	47f4412d 	ldrbmi	r4, [r4, sp, lsr #2]!
47f303e8:	47f4413c 			@ <UNDEFINED> instruction: 0x47f4413c
47f303ec:	e59f3028 	ldr	r3, [pc, #40]	@ 0x47f3041c
47f303f0:	e5932000 	ldr	r2, [r3]
47f303f4:	e59f3024 	ldr	r3, [pc, #36]	@ 0x47f30420
47f303f8:	e1520003 	cmp	r2, r3
47f303fc:	e3a03325 	mov	r3, #-1811939328	@ 0x94000000
47f30400:	1a000002 	bne	0x47f30410
47f30404:	e5930074 	ldr	r0, [r3, #116]	@ 0x74
47f30408:	e2000003 	and	r0, r0, #3
47f3040c:	e12fff1e 	bx	lr
47f30410:	e5930040 	ldr	r0, [r3, #64]	@ 0x40
47f30414:	e7e10350 	ubfx	r0, r0, #6, #2
47f30418:	e12fff1e 	bx	lr
47f3041c:	92040000 	andls	r0, r4, #0
47f30420:	27912710 			@ <UNDEFINED> instruction: 0x27912710
47f30424:	e59f302c 	ldr	r3, [pc, #44]	@ 0x47f30458
47f30428:	e5932004 	ldr	r2, [r3, #4]
47f3042c:	e3a03014 	mov	r3, #20
47f30430:	e0000093 	mul	r0, r3, r0
47f30434:	e5923028 	ldr	r3, [r2, #40]	@ 0x28
47f30438:	e0832000 	add	r2, r3, r0
47f3043c:	e592200c 	ldr	r2, [r2, #12]
47f30440:	e3520001 	cmp	r2, #1
47f30444:	07933000 	ldreq	r3, [r3, r0]
47f30448:	03a00000 	moveq	r0, #0
47f3044c:	13e00000 	mvnne	r0, #0
47f30450:	05813000 	streq	r3, [r1]
47f30454:	e12fff1e 	bx	lr
47f30458:	47f6218c 	ldrbmi	r2, [r6, r12, lsl #3]!
47f3045c:	e59f300c 	ldr	r3, [pc, #12]	@ 0x47f30470
47f30460:	e5930004 	ldr	r0, [r3, #4]
47f30464:	e3500000 	cmp	r0, #0
47f30468:	15d00044 	ldrbne	r0, [r0, #68]	@ 0x44
47f3046c:	e12fff1e 	bx	lr
47f30470:	47f6218c 	ldrbmi	r2, [r6, r12, lsl #3]!
47f30474:	e59f3034 	ldr	r3, [pc, #52]	@ 0x47f304b0
47f30478:	e5d33008 	ldrb	r3, [r3, #8]
47f3047c:	e243300c 	sub	r3, r3, #12
47f30480:	e6ef3073 	uxtb	r3, r3
47f30484:	e353001d 	cmp	r3, #29
47f30488:	8a000006 	bhi	0x47f304a8
47f3048c:	e3a02001 	mov	r2, #1
47f30490:	e59f001c 	ldr	r0, [pc, #28]	@ 0x47f304b4
47f30494:	e1a03312 	lsl	r3, r2, r3
47f30498:	e0000003 	and	r0, r0, r3
47f3049c:	e2900000 	adds	r0, r0, #0
47f304a0:	13a00001 	movne	r0, #1
47f304a4:	e12fff1e 	bx	lr
47f304a8:	e3a00000 	mov	r0, #0
47f304ac:	e12fff1e 	bx	lr
47f304b0:	47f6218c 	ldrbmi	r2, [r6, r12, lsl #3]!
47f304b4:	3f800003 	svccc	0x00800003
47f304b8:	e59f3028 	ldr	r3, [pc, #40]	@ 0x47f304e8
47f304bc:	e5d33008 	ldrb	r3, [r3, #8]
47f304c0:	e3530052 	cmp	r3, #82	@ 0x52
47f304c4:	0a000003 	beq	0x47f304d8
47f304c8:	e3530071 	cmp	r3, #113	@ 0x71
47f304cc:	0a000001 	beq	0x47f304d8
47f304d0:	e3530050 	cmp	r3, #80	@ 0x50
47f304d4:	1a000001 	bne	0x47f304e0
47f304d8:	e3a00001 	mov	r0, #1
47f304dc:	e12fff1e 	bx	lr
47f304e0:	e3a00000 	mov	r0, #0
47f304e4:	e12fff1e 	bx	lr
47f304e8:	47f6218c 	ldrbmi	r2, [r6, r12, lsl #3]!
47f304ec:	e59f3084 	ldr	r3, [pc, #132]	@ 0x47f30578
47f304f0:	e5d33008 	ldrb	r3, [r3, #8]
47f304f4:	e3530066 	cmp	r3, #102	@ 0x66
47f304f8:	8a00000d 	bhi	0x47f30534
47f304fc:	e3530064 	cmp	r3, #100	@ 0x64
47f30500:	2a000018 	bcs	0x47f30568
47f30504:	e3530031 	cmp	r3, #49	@ 0x31
47f30508:	8a000003 	bhi	0x47f3051c
47f3050c:	e3530030 	cmp	r3, #48	@ 0x30
47f30510:	2a000014 	bcs	0x47f30568
47f30514:	e353000f 	cmp	r3, #15
47f30518:	ea00000a 	b	0x47f30548
47f3051c:	e3530059 	cmp	r3, #89	@ 0x59
47f30520:	0a000010 	beq	0x47f30568
47f30524:	e353005e 	cmp	r3, #94	@ 0x5e
47f30528:	0a00000e 	beq	0x47f30568
47f3052c:	e3530034 	cmp	r3, #52	@ 0x34
47f30530:	ea000004 	b	0x47f30548
47f30534:	e353006d 	cmp	r3, #109	@ 0x6d
47f30538:	8a000004 	bhi	0x47f30550
47f3053c:	e353006c 	cmp	r3, #108	@ 0x6c
47f30540:	2a000008 	bcs	0x47f30568
47f30544:	e3530068 	cmp	r3, #104	@ 0x68
47f30548:	1a000008 	bne	0x47f30570
47f3054c:	ea000005 	b	0x47f30568
47f30550:	e3530074 	cmp	r3, #116	@ 0x74
47f30554:	0a000003 	beq	0x47f30568
47f30558:	3a000004 	bcc	0x47f30570
47f3055c:	e2433086 	sub	r3, r3, #134	@ 0x86
47f30560:	e3530005 	cmp	r3, #5
47f30564:	8a000001 	bhi	0x47f30570
47f30568:	e3a00001 	mov	r0, #1
47f3056c:	e12fff1e 	bx	lr
47f30570:	e3a00000 	mov	r0, #0
47f30574:	e12fff1e 	bx	lr
47f30578:	47f6218c 	ldrbmi	r2, [r6, r12, lsl #3]!
47f3057c:	e59f3058 	ldr	r3, [pc, #88]	@ 0x47f305dc
47f30580:	e5d33008 	ldrb	r3, [r3, #8]
47f30584:	e353004b 	cmp	r3, #75	@ 0x4b
47f30588:	8a000008 	bhi	0x47f305b0
47f3058c:	e353004a 	cmp	r3, #74	@ 0x4a
47f30590:	2a00000d 	bcs	0x47f305cc
47f30594:	e3530038 	cmp	r3, #56	@ 0x38
47f30598:	3a00000d 	bcc	0x47f305d4
47f3059c:	e3530039 	cmp	r3, #57	@ 0x39
47f305a0:	9a000009 	bls	0x47f305cc
47f305a4:	e2433042 	sub	r3, r3, #66	@ 0x42
47f305a8:	e3530001 	cmp	r3, #1
47f305ac:	ea000005 	b	0x47f305c8
47f305b0:	e353007f 	cmp	r3, #127	@ 0x7f
47f305b4:	3a000006 	bcc	0x47f305d4
47f305b8:	e3530080 	cmp	r3, #128	@ 0x80
47f305bc:	9a000002 	bls	0x47f305cc
47f305c0:	e2433090 	sub	r3, r3, #144	@ 0x90
47f305c4:	e3530002 	cmp	r3, #2
47f305c8:	8a000001 	bhi	0x47f305d4
47f305cc:	e3a00001 	mov	r0, #1
47f305d0:	e12fff1e 	bx	lr
47f305d4:	e3a00000 	mov	r0, #0
47f305d8:	e12fff1e 	bx	lr
47f305dc:	47f6218c 	ldrbmi	r2, [r6, r12, lsl #3]!
47f305e0:	e92d40f8 	push	{r3, r4, r5, r6, r7, lr}
47f305e4:	e3a05000 	mov	r5, #0
47f305e8:	e59f60ac 	ldr	r6, [pc, #172]	@ 0x47f3069c
47f305ec:	e5963004 	ldr	r3, [r6, #4]
47f305f0:	e5d32030 	ldrb	r2, [r3, #48]	@ 0x30
47f305f4:	e1550002 	cmp	r5, r2
47f305f8:	aa000026 	bge	0x47f30698
47f305fc:	e3a04014 	mov	r4, #20
47f30600:	e5932038 	ldr	r2, [r3, #56]	@ 0x38
47f30604:	e0040594 	mul	r4, r4, r5
47f30608:	e0823004 	add	r3, r2, r4
47f3060c:	e593100c 	ldr	r1, [r3, #12]
47f30610:	e3510001 	cmp	r1, #1
47f30614:	1a00001d 	bne	0x47f30690
47f30618:	e5d31004 	ldrb	r1, [r3, #4]
47f3061c:	e3510001 	cmp	r1, #1
47f30620:	1a00001a 	bne	0x47f30690
47f30624:	e7920004 	ldr	r0, [r2, r4]
47f30628:	e5931008 	ldr	r1, [r3, #8]
47f3062c:	ebfffd4f 	bl	0x47f2fb70
47f30630:	e5963004 	ldr	r3, [r6, #4]
47f30634:	e5933038 	ldr	r3, [r3, #56]	@ 0x38
47f30638:	e7930004 	ldr	r0, [r3, r4]
47f3063c:	ebfffd65 	bl	0x47f2fbd8
47f30640:	e5963004 	ldr	r3, [r6, #4]
47f30644:	e5933038 	ldr	r3, [r3, #56]	@ 0x38
47f30648:	e0832004 	add	r2, r3, r4
47f3064c:	e7930004 	ldr	r0, [r3, r4]
47f30650:	e5927008 	ldr	r7, [r2, #8]
47f30654:	ebfffd39 	bl	0x47f2fb40
47f30658:	e1570000 	cmp	r7, r0
47f3065c:	0a00000b 	beq	0x47f30690
47f30660:	e5963004 	ldr	r3, [r6, #4]
47f30664:	e5933038 	ldr	r3, [r3, #56]	@ 0x38
47f30668:	e0832004 	add	r2, r3, r4
47f3066c:	e7934004 	ldr	r4, [r3, r4]
47f30670:	e5927008 	ldr	r7, [r2, #8]
47f30674:	e1a00004 	mov	r0, r4
47f30678:	ebfffd30 	bl	0x47f2fb40
47f3067c:	e1a01004 	mov	r1, r4
47f30680:	e1a02007 	mov	r2, r7
47f30684:	e1a03000 	mov	r3, r0
47f30688:	e59f0010 	ldr	r0, [pc, #16]	@ 0x47f306a0
47f3068c:	ebff67b1 	bl	0x47f0a558
47f30690:	e2855001 	add	r5, r5, #1
47f30694:	eaffffd4 	b	0x47f305ec
47f30698:	e8bd80f8 	pop	{r3, r4, r5, r6, r7, pc}
47f3069c:	47f6218c 	ldrbmi	r2, [r6, r12, lsl #3]!
47f306a0:	47f4414e 	ldrbmi	r4, [r4, lr, asr #2]!
47f306a4:	e92d40f8 	push	{r3, r4, r5, r6, r7, lr}
47f306a8:	e3a05000 	mov	r5, #0
47f306ac:	e59f60b8 	ldr	r6, [pc, #184]	@ 0x47f3076c
47f306b0:	e5963004 	ldr	r3, [r6, #4]
47f306b4:	e5d32030 	ldrb	r2, [r3, #48]	@ 0x30
47f306b8:	e1550002 	cmp	r5, r2
47f306bc:	aa000029 	bge	0x47f30768
47f306c0:	e2452005 	sub	r2, r5, #5
47f306c4:	e3520001 	cmp	r2, #1
47f306c8:	8a000024 	bhi	0x47f30760
47f306cc:	e3a04014 	mov	r4, #20
47f306d0:	e5932038 	ldr	r2, [r3, #56]	@ 0x38
47f306d4:	e0040594 	mul	r4, r4, r5
47f306d8:	e0823004 	add	r3, r2, r4
47f306dc:	e593100c 	ldr	r1, [r3, #12]
47f306e0:	e3510001 	cmp	r1, #1
47f306e4:	1a00001d 	bne	0x47f30760
47f306e8:	e5d31004 	ldrb	r1, [r3, #4]
47f306ec:	e3510001 	cmp	r1, #1
47f306f0:	1a00001a 	bne	0x47f30760
47f306f4:	e7920004 	ldr	r0, [r2, r4]
47f306f8:	e5931008 	ldr	r1, [r3, #8]
47f306fc:	ebfffd1b 	bl	0x47f2fb70
47f30700:	e5963004 	ldr	r3, [r6, #4]
47f30704:	e5933038 	ldr	r3, [r3, #56]	@ 0x38
47f30708:	e7930004 	ldr	r0, [r3, r4]
47f3070c:	ebfffd31 	bl	0x47f2fbd8
47f30710:	e5963004 	ldr	r3, [r6, #4]
47f30714:	e5933038 	ldr	r3, [r3, #56]	@ 0x38
47f30718:	e0832004 	add	r2, r3, r4
47f3071c:	e7930004 	ldr	r0, [r3, r4]
47f30720:	e5927008 	ldr	r7, [r2, #8]
47f30724:	ebfffd05 	bl	0x47f2fb40
47f30728:	e1570000 	cmp	r7, r0
47f3072c:	0a00000b 	beq	0x47f30760
47f30730:	e5963004 	ldr	r3, [r6, #4]
47f30734:	e5933038 	ldr	r3, [r3, #56]	@ 0x38
47f30738:	e0832004 	add	r2, r3, r4
47f3073c:	e7934004 	ldr	r4, [r3, r4]
47f30740:	e5927008 	ldr	r7, [r2, #8]
47f30744:	e1a00004 	mov	r0, r4
47f30748:	ebfffcfc 	bl	0x47f2fb40
47f3074c:	e1a01004 	mov	r1, r4
47f30750:	e1a02007 	mov	r2, r7
47f30754:	e1a03000 	mov	r3, r0
47f30758:	e59f0010 	ldr	r0, [pc, #16]	@ 0x47f30770
47f3075c:	ebff677d 	bl	0x47f0a558
47f30760:	e2855001 	add	r5, r5, #1
47f30764:	eaffffd1 	b	0x47f306b0
47f30768:	e8bd80f8 	pop	{r3, r4, r5, r6, r7, pc}
47f3076c:	47f6218c 	ldrbmi	r2, [r6, r12, lsl #3]!
47f30770:	47f4414e 	ldrbmi	r4, [r4, lr, asr #2]!
47f30774:	e92d4008 	push	{r3, lr}
47f30778:	ebffff37 	bl	0x47f3045c
47f3077c:	e3500000 	cmp	r0, #0
47f30780:	159f3008 	ldrne	r3, [pc, #8]	@ 0x47f30790
47f30784:	15930004 	ldrne	r0, [r3, #4]
47f30788:	1280003c 	addne	r0, r0, #60	@ 0x3c
47f3078c:	e8bd8008 	pop	{r3, pc}
47f30790:	47f6218c 	ldrbmi	r2, [r6, r12, lsl #3]!
47f30794:	e92d4037 	push	{r0, r1, r2, r4, r5, lr}
47f30798:	e28d1008 	add	r1, sp, #8
47f3079c:	e3a03000 	mov	r3, #0
47f307a0:	e3a00011 	mov	r0, #17
47f307a4:	e5213004 	str	r3, [r1, #-4]!
47f307a8:	ebffff1d 	bl	0x47f30424
47f307ac:	e3500000 	cmp	r0, #0
47f307b0:	a3a05015 	movge	r5, #21
47f307b4:	aa000007 	bge	0x47f307d8
47f307b8:	e59f0034 	ldr	r0, [pc, #52]	@ 0x47f307f4
47f307bc:	ebff6765 	bl	0x47f0a558
47f307c0:	e3a00001 	mov	r0, #1
47f307c4:	ea000008 	b	0x47f307ec
47f307c8:	e59f0028 	ldr	r0, [pc, #40]	@ 0x47f307f8
47f307cc:	ebffd848 	bl	0x47f268f4
47f307d0:	e2555001 	subs	r5, r5, #1
47f307d4:	0a000003 	beq	0x47f307e8
47f307d8:	e59d0004 	ldr	r0, [sp, #4]
47f307dc:	ebfffcd7 	bl	0x47f2fb40
47f307e0:	e2504000 	subs	r4, r0, #0
47f307e4:	0afffff7 	beq	0x47f307c8
47f307e8:	e1a00004 	mov	r0, r4
47f307ec:	e28dd00c 	add	sp, sp, #12
47f307f0:	e8bd8030 	pop	{r4, r5, pc}
47f307f4:	47f4416c 	ldrbmi	r4, [r4, r12, ror #2]!
47f307f8:	0003d090 	muleq	r3, r0, r0
47f307fc:	e59f338c 	ldr	r3, [pc, #908]	@ 0x47f30b90
47f30800:	e92d46f7 	push	{r0, r1, r2, r4, r5, r6, r7, r9, r10, lr}
47f30804:	e3a05000 	mov	r5, #0
47f30808:	e58d5004 	str	r5, [sp, #4]
47f3080c:	e5936000 	ldr	r6, [r3]
47f30810:	e59f737c 	ldr	r7, [pc, #892]	@ 0x47f30b94
47f30814:	e1a01006 	mov	r1, r6
47f30818:	e59f0378 	ldr	r0, [pc, #888]	@ 0x47f30b98
47f3081c:	ebff674d 	bl	0x47f0a558
47f30820:	e1560007 	cmp	r6, r7
47f30824:	e59f4370 	ldr	r4, [pc, #880]	@ 0x47f30b9c
47f30828:	0a000042 	beq	0x47f30938
47f3082c:	ca000003 	bgt	0x47f30840
47f30830:	e59f3368 	ldr	r3, [pc, #872]	@ 0x47f30ba0
47f30834:	e1560003 	cmp	r6, r3
47f30838:	0a000007 	beq	0x47f3085c
47f3083c:	ea00004f 	b	0x47f30980
47f30840:	e59f335c 	ldr	r3, [pc, #860]	@ 0x47f30ba4
47f30844:	e1560003 	cmp	r6, r3
47f30848:	0a000016 	beq	0x47f308a8
47f3084c:	e2833010 	add	r3, r3, #16
47f30850:	e1560003 	cmp	r6, r3
47f30854:	0a000025 	beq	0x47f308f0
47f30858:	ea000048 	b	0x47f30980
47f3085c:	ebfffd7a 	bl	0x47f2fe4c
47f30860:	e59f6340 	ldr	r6, [pc, #832]	@ 0x47f30ba8
47f30864:	ebfffd38 	bl	0x47f2fd4c
47f30868:	e3a0304c 	mov	r3, #76	@ 0x4c
47f3086c:	e0236093 	mla	r3, r3, r0, r6
47f30870:	e1a01000 	mov	r1, r0
47f30874:	e5c40008 	strb	r0, [r4, #8]
47f30878:	e5843004 	str	r3, [r4, #4]
47f3087c:	e5933008 	ldr	r3, [r3, #8]
47f30880:	e1500003 	cmp	r0, r3
47f30884:	0a000005 	beq	0x47f308a0
47f30888:	e59f031c 	ldr	r0, [pc, #796]	@ 0x47f30bac
47f3088c:	e3003173 	movw	r3, #371	@ 0x173
47f30890:	e59f2318 	ldr	r2, [pc, #792]	@ 0x47f30bb0
47f30894:	ebff672f 	bl	0x47f0a558
47f30898:	e5c45008 	strb	r5, [r4, #8]
47f3089c:	e5846004 	str	r6, [r4, #4]
47f308a0:	e3a03000 	mov	r3, #0
47f308a4:	ea000038 	b	0x47f3098c
47f308a8:	ebfffdb6 	bl	0x47f2ff88
47f308ac:	ebfffd75 	bl	0x47f2fe88
47f308b0:	e3a0204c 	mov	r2, #76	@ 0x4c
47f308b4:	e59f32ec 	ldr	r3, [pc, #748]	@ 0x47f30ba8
47f308b8:	e283604c 	add	r6, r3, #76	@ 0x4c
47f308bc:	e0020092 	mul	r2, r2, r0
47f308c0:	e1a01000 	mov	r1, r0
47f308c4:	e5c40008 	strb	r0, [r4, #8]
47f308c8:	e0833002 	add	r3, r3, r2
47f308cc:	e0860002 	add	r0, r6, r2
47f308d0:	e5840004 	str	r0, [r4, #4]
47f308d4:	e5933054 	ldr	r3, [r3, #84]	@ 0x54
47f308d8:	e1510003 	cmp	r1, r3
47f308dc:	0affffef 	beq	0x47f308a0
47f308e0:	e59f02c4 	ldr	r0, [pc, #708]	@ 0x47f30bac
47f308e4:	e300317f 	movw	r3, #383	@ 0x17f
47f308e8:	e59f22c0 	ldr	r2, [pc, #704]	@ 0x47f30bb0
47f308ec:	eaffffe8 	b	0x47f30894
47f308f0:	ebfffdf9 	bl	0x47f300dc
47f308f4:	ebfffdb8 	bl	0x47f2ffdc
47f308f8:	e3a0204c 	mov	r2, #76	@ 0x4c
47f308fc:	e59f32a4 	ldr	r3, [pc, #676]	@ 0x47f30ba8
47f30900:	e2836098 	add	r6, r3, #152	@ 0x98
47f30904:	e0020092 	mul	r2, r2, r0
47f30908:	e1a01000 	mov	r1, r0
47f3090c:	e5c40008 	strb	r0, [r4, #8]
47f30910:	e0833002 	add	r3, r3, r2
47f30914:	e0860002 	add	r0, r6, r2
47f30918:	e5840004 	str	r0, [r4, #4]
47f3091c:	e59330a0 	ldr	r3, [r3, #160]	@ 0xa0
47f30920:	e1510003 	cmp	r1, r3
47f30924:	0affffdd 	beq	0x47f308a0
47f30928:	e59f027c 	ldr	r0, [pc, #636]	@ 0x47f30bac
47f3092c:	e300318b 	movw	r3, #395	@ 0x18b
47f30930:	e59f2278 	ldr	r2, [pc, #632]	@ 0x47f30bb0
47f30934:	eaffffd6 	b	0x47f30894
47f30938:	ebfffe44 	bl	0x47f30250
47f3093c:	ebfffe03 	bl	0x47f30150
47f30940:	e3a0204c 	mov	r2, #76	@ 0x4c
47f30944:	e59f3268 	ldr	r3, [pc, #616]	@ 0x47f30bb4
47f30948:	e2436d2a 	sub	r6, r3, #2688	@ 0xa80
47f3094c:	e0020092 	mul	r2, r2, r0
47f30950:	e1a01000 	mov	r1, r0
47f30954:	e5c40008 	strb	r0, [r4, #8]
47f30958:	e0833002 	add	r3, r3, r2
47f3095c:	e0860002 	add	r0, r6, r2
47f30960:	e5840004 	str	r0, [r4, #4]
47f30964:	e5133a78 	ldr	r3, [r3, #-2680]	@ 0xfffff588
47f30968:	e1510003 	cmp	r1, r3
47f3096c:	0affffcb 	beq	0x47f308a0
47f30970:	e59f0234 	ldr	r0, [pc, #564]	@ 0x47f30bac
47f30974:	e3003197 	movw	r3, #407	@ 0x197
47f30978:	e59f2230 	ldr	r2, [pc, #560]	@ 0x47f30bb0
47f3097c:	eaffffc4 	b	0x47f30894
47f30980:	e59f0230 	ldr	r0, [pc, #560]	@ 0x47f30bb8
47f30984:	ebff66f3 	bl	0x47f0a558
47f30988:	eaffffc4 	b	0x47f308a0
47f3098c:	e2832425 	add	r2, r3, #620756992	@ 0x25000000
47f30990:	e2822702 	add	r2, r2, #524288	@ 0x80000
47f30994:	e1a02102 	lsl	r2, r2, #2
47f30998:	e58d2004 	str	r2, [sp, #4]
47f3099c:	e5942004 	ldr	r2, [r4, #4]
47f309a0:	e0822103 	add	r2, r2, r3, lsl #2
47f309a4:	e5921018 	ldr	r1, [r2, #24]
47f309a8:	e59d2004 	ldr	r2, [sp, #4]
47f309ac:	e2833001 	add	r3, r3, #1
47f309b0:	e3530004 	cmp	r3, #4
47f309b4:	e5821000 	str	r1, [r2]
47f309b8:	1afffff3 	bne	0x47f3098c
47f309bc:	e59fa1d8 	ldr	r10, [pc, #472]	@ 0x47f30b9c
47f309c0:	e3a06000 	mov	r6, #0
47f309c4:	e5943004 	ldr	r3, [r4, #4]
47f309c8:	e593202c 	ldr	r2, [r3, #44]	@ 0x2c
47f309cc:	e1560002 	cmp	r6, r2
47f309d0:	2a000030 	bcs	0x47f30a98
47f309d4:	e3a05014 	mov	r5, #20
47f309d8:	e5933028 	ldr	r3, [r3, #40]	@ 0x28
47f309dc:	e0050695 	mul	r5, r5, r6
47f309e0:	e0832005 	add	r2, r3, r5
47f309e4:	e592100c 	ldr	r1, [r2, #12]
47f309e8:	e3510001 	cmp	r1, #1
47f309ec:	1a000027 	bne	0x47f30a90
47f309f0:	e5d29004 	ldrb	r9, [r2, #4]
47f309f4:	e3590001 	cmp	r9, #1
47f309f8:	1a000020 	bne	0x47f30a80
47f309fc:	e7930005 	ldr	r0, [r3, r5]
47f30a00:	ebfffc74 	bl	0x47f2fbd8
47f30a04:	e1a00009 	mov	r0, r9
47f30a08:	ebffd7c5 	bl	0x47f26924
47f30a0c:	e59a3004 	ldr	r3, [r10, #4]
47f30a10:	e5933028 	ldr	r3, [r3, #40]	@ 0x28
47f30a14:	e0832005 	add	r2, r3, r5
47f30a18:	e7930005 	ldr	r0, [r3, r5]
47f30a1c:	e5921008 	ldr	r1, [r2, #8]
47f30a20:	ebfffc52 	bl	0x47f2fb70
47f30a24:	e1a00009 	mov	r0, r9
47f30a28:	ebffd7bd 	bl	0x47f26924
47f30a2c:	e59a3004 	ldr	r3, [r10, #4]
47f30a30:	e5933028 	ldr	r3, [r3, #40]	@ 0x28
47f30a34:	e0832005 	add	r2, r3, r5
47f30a38:	e7930005 	ldr	r0, [r3, r5]
47f30a3c:	e5929008 	ldr	r9, [r2, #8]
47f30a40:	ebfffc3e 	bl	0x47f2fb40
47f30a44:	e1590000 	cmp	r9, r0
47f30a48:	0a000010 	beq	0x47f30a90
47f30a4c:	e59a3004 	ldr	r3, [r10, #4]
47f30a50:	e5933028 	ldr	r3, [r3, #40]	@ 0x28
47f30a54:	e0832005 	add	r2, r3, r5
47f30a58:	e7935005 	ldr	r5, [r3, r5]
47f30a5c:	e5929008 	ldr	r9, [r2, #8]
47f30a60:	e1a00005 	mov	r0, r5
47f30a64:	ebfffc35 	bl	0x47f2fb40
47f30a68:	e1a01005 	mov	r1, r5
47f30a6c:	e1a02009 	mov	r2, r9
47f30a70:	e1a03000 	mov	r3, r0
47f30a74:	e59f0140 	ldr	r0, [pc, #320]	@ 0x47f30bbc
47f30a78:	ebff66b6 	bl	0x47f0a558
47f30a7c:	ea000003 	b	0x47f30a90
47f30a80:	e3590000 	cmp	r9, #0
47f30a84:	1a000001 	bne	0x47f30a90
47f30a88:	e7930005 	ldr	r0, [r3, r5]
47f30a8c:	ebfffc47 	bl	0x47f2fbb0
47f30a90:	e2866001 	add	r6, r6, #1
47f30a94:	eaffffca 	b	0x47f309c4
47f30a98:	e59f90fc 	ldr	r9, [pc, #252]	@ 0x47f30b9c
47f30a9c:	e3a05000 	mov	r5, #0
47f30aa0:	e5943004 	ldr	r3, [r4, #4]
47f30aa4:	e59f60f0 	ldr	r6, [pc, #240]	@ 0x47f30b9c
47f30aa8:	e593202c 	ldr	r2, [r3, #44]	@ 0x2c
47f30aac:	e1550002 	cmp	r5, r2
47f30ab0:	2a00001e 	bcs	0x47f30b30
47f30ab4:	e3a06014 	mov	r6, #20
47f30ab8:	e5933028 	ldr	r3, [r3, #40]	@ 0x28
47f30abc:	e0060596 	mul	r6, r6, r5
47f30ac0:	e0832006 	add	r2, r3, r6
47f30ac4:	e592100c 	ldr	r1, [r2, #12]
47f30ac8:	e3510001 	cmp	r1, #1
47f30acc:	1a000015 	bne	0x47f30b28
47f30ad0:	e5d2a004 	ldrb	r10, [r2, #4]
47f30ad4:	e35a0001 	cmp	r10, #1
47f30ad8:	1a000012 	bne	0x47f30b28
47f30adc:	e2452041 	sub	r2, r5, #65	@ 0x41
47f30ae0:	e3520001 	cmp	r2, #1
47f30ae4:	8a00000f 	bhi	0x47f30b28
47f30ae8:	e7930006 	ldr	r0, [r3, r6]
47f30aec:	e3a01000 	mov	r1, #0
47f30af0:	ebfffc1e 	bl	0x47f2fb70
47f30af4:	e3a000c8 	mov	r0, #200	@ 0xc8
47f30af8:	ebffd789 	bl	0x47f26924
47f30afc:	e5993004 	ldr	r3, [r9, #4]
47f30b00:	e1a0100a 	mov	r1, r10
47f30b04:	e5933028 	ldr	r3, [r3, #40]	@ 0x28
47f30b08:	e7930006 	ldr	r0, [r3, r6]
47f30b0c:	ebfffc17 	bl	0x47f2fb70
47f30b10:	e5993004 	ldr	r3, [r9, #4]
47f30b14:	e59f00a4 	ldr	r0, [pc, #164]	@ 0x47f30bc0
47f30b18:	e1a01005 	mov	r1, r5
47f30b1c:	e5933028 	ldr	r3, [r3, #40]	@ 0x28
47f30b20:	e7932006 	ldr	r2, [r3, r6]
47f30b24:	ebff668b 	bl	0x47f0a558
47f30b28:	e2855001 	add	r5, r5, #1
47f30b2c:	eaffffdb 	b	0x47f30aa0
47f30b30:	e5933014 	ldr	r3, [r3, #20]
47f30b34:	e5c63000 	strb	r3, [r6]
47f30b38:	ebfffe2b 	bl	0x47f303ec
47f30b3c:	e1a01000 	mov	r1, r0
47f30b40:	e586000c 	str	r0, [r6, #12]
47f30b44:	e59f0078 	ldr	r0, [pc, #120]	@ 0x47f30bc4
47f30b48:	ebff6682 	bl	0x47f0a558
47f30b4c:	e59f303c 	ldr	r3, [pc, #60]	@ 0x47f30b90
47f30b50:	e5932000 	ldr	r2, [r3]
47f30b54:	e1520007 	cmp	r2, r7
47f30b58:	1a000003 	bne	0x47f30b6c
47f30b5c:	e3a03325 	mov	r3, #-1811939328	@ 0x94000000
47f30b60:	e3a02031 	mov	r2, #49	@ 0x31
47f30b64:	e5832008 	str	r2, [r3, #8]
47f30b68:	ea000006 	b	0x47f30b88
47f30b6c:	e5932000 	ldr	r2, [r3]
47f30b70:	e59f3050 	ldr	r3, [pc, #80]	@ 0x47f30bc8
47f30b74:	e1520003 	cmp	r2, r3
47f30b78:	1a000002 	bne	0x47f30b88
47f30b7c:	e3a03325 	mov	r3, #-1811939328	@ 0x94000000
47f30b80:	e30021fb 	movw	r2, #507	@ 0x1fb
47f30b84:	e5832004 	str	r2, [r3, #4]
47f30b88:	e28dd00c 	add	sp, sp, #12
47f30b8c:	e8bd86f0 	pop	{r4, r5, r6, r7, r9, r10, pc}
47f30b90:	92040000 	andls	r0, r4, #0
47f30b94:	27912710 			@ <UNDEFINED> instruction: 0x27912710
47f30b98:	47f44183 	ldrbmi	r4, [r4, r3, lsl #3]!
47f30b9c:	47f6218c 	ldrbmi	r2, [r6, r12, lsl #3]!
47f30ba0:	27912700 	ldrcs	r2, [r1, r0, lsl #14]
47f30ba4:	27912800 	ldrcs	r2, [r1, r0, lsl #16]
47f30ba8:	47f4766c 	ldrbmi	r7, [r4, r12, ror #12]!
47f30bac:	47f4418d 	ldrbmi	r4, [r4, sp, lsl #3]!
47f30bb0:	47f3a5a2 	ldrbmi	r10, [r3, r2, lsr #11]!
47f30bb4:	47f4b65c 	ubfxmi	r11, r12, #12, #21
47f30bb8:	47f441a4 	ldrbmi	r4, [r4, r4, lsr #3]!
47f30bbc:	47f4414e 	ldrbmi	r4, [r4, lr, asr #2]!
47f30bc0:	47f441b2 			@ <UNDEFINED> instruction: 0x47f441b2
47f30bc4:	47f441c3 	ldrbmi	r4, [r4, r3, asr #3]!
47f30bc8:	27912810 			@ <UNDEFINED> instruction: 0x27912810
47f30bcc:	e1a012a1 	lsr	r1, r1, #5
47f30bd0:	e260368f 	rsb	r3, r0, #149946368	@ 0x8f00000
47f30bd4:	e2612008 	rsb	r2, r1, #8
47f30bd8:	e2833f42 	add	r3, r3, #264	@ 0x108
47f30bdc:	e0801101 	add	r1, r0, r1, lsl #2
47f30be0:	e0833102 	add	r3, r3, r2, lsl #2
47f30be4:	e1500001 	cmp	r0, r1
47f30be8:	10832000 	addne	r2, r3, r0
47f30bec:	1490c004 	ldrne	r12, [r0], #4
47f30bf0:	1582c000 	strne	r12, [r2]
47f30bf4:	1afffffa 	bne	0x47f30be4
47f30bf8:	e12fff1e 	bx	lr
47f30bfc:	e5902000 	ldr	r2, [r0]
47f30c00:	e3a0368f 	mov	r3, #149946368	@ 0x8f00000
47f30c04:	e5832128 	str	r2, [r3, #296]	@ 0x128
47f30c08:	e5902004 	ldr	r2, [r0, #4]
47f30c0c:	e583212c 	str	r2, [r3, #300]	@ 0x12c
47f30c10:	e5902008 	ldr	r2, [r0, #8]
47f30c14:	e5832130 	str	r2, [r3, #304]	@ 0x130
47f30c18:	e590200c 	ldr	r2, [r0, #12]
47f30c1c:	e5832134 	str	r2, [r3, #308]	@ 0x134
47f30c20:	e12fff1e 	bx	lr
47f30c24:	e0800102 	add	r0, r0, r2, lsl #2
47f30c28:	e3a03000 	mov	r3, #0
47f30c2c:	e1530002 	cmp	r3, r2
47f30c30:	1530c004 	ldrne	r12, [r0, #-4]!
47f30c34:	1781c103 	strne	r12, [r1, r3, lsl #2]
47f30c38:	12833001 	addne	r3, r3, #1
47f30c3c:	1afffffa 	bne	0x47f30c2c
47f30c40:	e12fff1e 	bx	lr
47f30c44:	e92d4010 	push	{r4, lr}
47f30c48:	e3a04ffa 	mov	r4, #1000	@ 0x3e8
47f30c4c:	e3a00ffa 	mov	r0, #1000	@ 0x3e8
47f30c50:	ebffd727 	bl	0x47f268f4
47f30c54:	e2544001 	subs	r4, r4, #1
47f30c58:	1afffffb 	bne	0x47f30c4c
47f30c5c:	e1a00004 	mov	r0, r4
47f30c60:	e1a01004 	mov	r1, r4
47f30c64:	e1a02004 	mov	r2, r4
47f30c68:	e1a03004 	mov	r3, r4
47f30c6c:	e8bd4010 	pop	{r4, lr}
47f30c70:	eaff446e 	b	0x47f01e30
47f30c74:	e92d4ef3 	push	{r0, r1, r4, r5, r6, r7, r9, r10, r11, lr}
47f30c78:	e1a033a2 	lsr	r3, r2, #7
47f30c7c:	e1a04002 	mov	r4, r2
47f30c80:	e58d3004 	str	r3, [sp, #4]
47f30c84:	e1a07000 	mov	r7, r0
47f30c88:	e202307f 	and	r3, r2, #127	@ 0x7f
47f30c8c:	e1a09001 	mov	r9, r1
47f30c90:	e1a0b001 	mov	r11, r1
47f30c94:	e1a02000 	mov	r2, r0
47f30c98:	e3a05000 	mov	r5, #0
47f30c9c:	e58d3000 	str	r3, [sp]
47f30ca0:	e59d3004 	ldr	r3, [sp, #4]
47f30ca4:	e1550003 	cmp	r5, r3
47f30ca8:	0a00001d 	beq	0x47f30d24
47f30cac:	e282a080 	add	r10, r2, #128	@ 0x80
47f30cb0:	e3a0068f 	mov	r0, #149946368	@ 0x8f00000
47f30cb4:	e492c004 	ldr	r12, [r2], #4
47f30cb8:	e152000a 	cmp	r2, r10
47f30cbc:	e580c14c 	str	r12, [r0, #332]	@ 0x14c
47f30cc0:	1afffffb 	bne	0x47f30cb4
47f30cc4:	e3a06020 	mov	r6, #32
47f30cc8:	e3a0268f 	mov	r2, #149946368	@ 0x8f00000
47f30ccc:	e5920148 	ldr	r0, [r2, #328]	@ 0x148
47f30cd0:	e200003f 	and	r0, r0, #63	@ 0x3f
47f30cd4:	e3500020 	cmp	r0, #32
47f30cd8:	0a000009 	beq	0x47f30d04
47f30cdc:	e3a0000a 	mov	r0, #10
47f30ce0:	e2866001 	add	r6, r6, #1
47f30ce4:	ebffd702 	bl	0x47f268f4
47f30ce8:	e59f30f8 	ldr	r3, [pc, #248]	@ 0x47f30de8
47f30cec:	e1560003 	cmp	r6, r3
47f30cf0:	9afffff4 	bls	0x47f30cc8
47f30cf4:	e59f00f0 	ldr	r0, [pc, #240]	@ 0x47f30dec
47f30cf8:	ebff6616 	bl	0x47f0a558
47f30cfc:	ebffffd0 	bl	0x47f30c44
47f30d00:	eafffff0 	b	0x47f30cc8
47f30d04:	e28b0080 	add	r0, r11, #128	@ 0x80
47f30d08:	e592c150 	ldr	r12, [r2, #336]	@ 0x150
47f30d0c:	e48bc004 	str	r12, [r11], #4
47f30d10:	e15b0000 	cmp	r11, r0
47f30d14:	1afffffb 	bne	0x47f30d08
47f30d18:	e2855001 	add	r5, r5, #1
47f30d1c:	e1a0200a 	mov	r2, r10
47f30d20:	eaffffde 	b	0x47f30ca0
47f30d24:	e59d3000 	ldr	r3, [sp]
47f30d28:	e1a05385 	lsl	r5, r5, #7
47f30d2c:	e0870005 	add	r0, r7, r5
47f30d30:	e0895005 	add	r5, r9, r5
47f30d34:	e3530000 	cmp	r3, #0
47f30d38:	0a000028 	beq	0x47f30de0
47f30d3c:	e1a06123 	lsr	r6, r3, #2
47f30d40:	e3a0268f 	mov	r2, #149946368	@ 0x8f00000
47f30d44:	e1a07106 	lsl	r7, r6, #2
47f30d48:	e0803007 	add	r3, r0, r7
47f30d4c:	e1500003 	cmp	r0, r3
47f30d50:	14901004 	ldrne	r1, [r0], #4
47f30d54:	1582114c 	strne	r1, [r2, #332]	@ 0x14c
47f30d58:	1afffffb 	bne	0x47f30d4c
47f30d5c:	e214401f 	ands	r4, r4, #31
47f30d60:	01a04006 	moveq	r4, r6
47f30d64:	0a000009 	beq	0x47f30d90
47f30d68:	e2644020 	rsb	r4, r4, #32
47f30d6c:	e3a03000 	mov	r3, #0
47f30d70:	e3a0268f 	mov	r2, #149946368	@ 0x8f00000
47f30d74:	e1a01003 	mov	r1, r3
47f30d78:	e1a04124 	lsr	r4, r4, #2
47f30d7c:	e1530004 	cmp	r3, r4
47f30d80:	1582114c 	strne	r1, [r2, #332]	@ 0x14c
47f30d84:	12833001 	addne	r3, r3, #1
47f30d88:	1afffffb 	bne	0x47f30d7c
47f30d8c:	e0866004 	add	r6, r6, r4
47f30d90:	e59f9050 	ldr	r9, [pc, #80]	@ 0x47f30de8
47f30d94:	e3a0368f 	mov	r3, #149946368	@ 0x8f00000
47f30d98:	e5932148 	ldr	r2, [r3, #328]	@ 0x148
47f30d9c:	e202203f 	and	r2, r2, #63	@ 0x3f
47f30da0:	e1520006 	cmp	r2, r6
47f30da4:	0a000008 	beq	0x47f30dcc
47f30da8:	e2844001 	add	r4, r4, #1
47f30dac:	e3a0000a 	mov	r0, #10
47f30db0:	ebffd6cf 	bl	0x47f268f4
47f30db4:	e1540009 	cmp	r4, r9
47f30db8:	9afffff5 	bls	0x47f30d94
47f30dbc:	e59f0028 	ldr	r0, [pc, #40]	@ 0x47f30dec
47f30dc0:	ebff65e4 	bl	0x47f0a558
47f30dc4:	ebffff9e 	bl	0x47f30c44
47f30dc8:	eafffff1 	b	0x47f30d94
47f30dcc:	e0857007 	add	r7, r5, r7
47f30dd0:	e1550007 	cmp	r5, r7
47f30dd4:	15932150 	ldrne	r2, [r3, #336]	@ 0x150
47f30dd8:	14852004 	strne	r2, [r5], #4
47f30ddc:	1afffffb 	bne	0x47f30dd0
47f30de0:	e28dd008 	add	sp, sp, #8
47f30de4:	e8bd8ef0 	pop	{r4, r5, r6, r7, r9, r10, r11, pc}
47f30de8:	000186a0 	andeq	r8, r1, r0, lsr #13
47f30dec:	47f44390 			@ <UNDEFINED> instruction: 0x47f44390
47f30df0:	e92d42f0 	push	{r4, r5, r6, r7, r9, lr}
47f30df4:	e1a07000 	mov	r7, r0
47f30df8:	e59d0018 	ldr	r0, [sp, #24]
47f30dfc:	e1a05002 	mov	r5, r2
47f30e00:	e3a02000 	mov	r2, #0
47f30e04:	e3a0c68f 	mov	r12, #149946368	@ 0x8f00000
47f30e08:	e1500002 	cmp	r0, r2
47f30e0c:	e1a06001 	mov	r6, r1
47f30e10:	e1a09003 	mov	r9, r3
47f30e14:	e3a01001 	mov	r1, #1
47f30e18:	e3a03084 	mov	r3, #132	@ 0x84
47f30e1c:	e58c1004 	str	r1, [r12, #4]
47f30e20:	e59f4064 	ldr	r4, [pc, #100]	@ 0x47f30e8c
47f30e24:	e58c2154 	str	r2, [r12, #340]	@ 0x154
47f30e28:	e58c3104 	str	r3, [r12, #260]	@ 0x104
47f30e2c:	158c200c 	strne	r2, [r12, #12]
47f30e30:	1a000004 	bne	0x47f30e48
47f30e34:	e58c100c 	str	r1, [r12, #12]
47f30e38:	e5943040 	ldr	r3, [r4, #64]	@ 0x40
47f30e3c:	e3530000 	cmp	r3, #0
47f30e40:	0afffffc 	beq	0x47f30e38
47f30e44:	ea000004 	b	0x47f30e5c
47f30e48:	e5943040 	ldr	r3, [r4, #64]	@ 0x40
47f30e4c:	e3530000 	cmp	r3, #0
47f30e50:	0afffffc 	beq	0x47f30e48
47f30e54:	e3a01c01 	mov	r1, #256	@ 0x100
47f30e58:	ebffff5b 	bl	0x47f30bcc
47f30e5c:	e1a00009 	mov	r0, r9
47f30e60:	e3a0468f 	mov	r4, #149946368	@ 0x8f00000
47f30e64:	ebffff64 	bl	0x47f30bfc
47f30e68:	e3a03001 	mov	r3, #1
47f30e6c:	e1a00007 	mov	r0, r7
47f30e70:	e5843154 	str	r3, [r4, #340]	@ 0x154
47f30e74:	e1a01006 	mov	r1, r6
47f30e78:	e1a02005 	mov	r2, r5
47f30e7c:	ebffff7c 	bl	0x47f30c74
47f30e80:	e3a00000 	mov	r0, #0
47f30e84:	e5840154 	str	r0, [r4, #340]	@ 0x154
47f30e88:	e8bd82f0 	pop	{r4, r5, r6, r7, r9, pc}
47f30e8c:	9a107000 	bls	0x4834ce94
47f30e90:	e92d42f0 	push	{r4, r5, r6, r7, r9, lr}
47f30e94:	e1a07000 	mov	r7, r0
47f30e98:	e59d0018 	ldr	r0, [sp, #24]
47f30e9c:	e1a05002 	mov	r5, r2
47f30ea0:	e3a02000 	mov	r2, #0
47f30ea4:	e3a0c68f 	mov	r12, #149946368	@ 0x8f00000
47f30ea8:	e1500002 	cmp	r0, r2
47f30eac:	e1a06001 	mov	r6, r1
47f30eb0:	e1a09003 	mov	r9, r3
47f30eb4:	e3a01001 	mov	r1, #1
47f30eb8:	e3a03004 	mov	r3, #4
47f30ebc:	e58c1004 	str	r1, [r12, #4]
47f30ec0:	e59f4064 	ldr	r4, [pc, #100]	@ 0x47f30f2c
47f30ec4:	e58c2154 	str	r2, [r12, #340]	@ 0x154
47f30ec8:	e58c3104 	str	r3, [r12, #260]	@ 0x104
47f30ecc:	158c200c 	strne	r2, [r12, #12]
47f30ed0:	1a000004 	bne	0x47f30ee8
47f30ed4:	e58c100c 	str	r1, [r12, #12]
47f30ed8:	e5943040 	ldr	r3, [r4, #64]	@ 0x40
47f30edc:	e3530000 	cmp	r3, #0
47f30ee0:	0afffffc 	beq	0x47f30ed8
47f30ee4:	ea000004 	b	0x47f30efc
47f30ee8:	e5943040 	ldr	r3, [r4, #64]	@ 0x40
47f30eec:	e3530000 	cmp	r3, #0
47f30ef0:	0afffffc 	beq	0x47f30ee8
47f30ef4:	e3a01080 	mov	r1, #128	@ 0x80
47f30ef8:	ebffff33 	bl	0x47f30bcc
47f30efc:	e1a00009 	mov	r0, r9
47f30f00:	e3a0468f 	mov	r4, #149946368	@ 0x8f00000
47f30f04:	ebffff3c 	bl	0x47f30bfc
47f30f08:	e3a03001 	mov	r3, #1
47f30f0c:	e1a00007 	mov	r0, r7
47f30f10:	e5843154 	str	r3, [r4, #340]	@ 0x154
47f30f14:	e1a01006 	mov	r1, r6
47f30f18:	e1a02005 	mov	r2, r5
47f30f1c:	ebffff54 	bl	0x47f30c74
47f30f20:	e3a00000 	mov	r0, #0
47f30f24:	e5840154 	str	r0, [r4, #340]	@ 0x154
47f30f28:	e8bd82f0 	pop	{r4, r5, r6, r7, r9, pc}
47f30f2c:	9a107000 	bls	0x4834cf34
47f30f30:	e92d42f0 	push	{r4, r5, r6, r7, r9, lr}
47f30f34:	e1a07000 	mov	r7, r0
47f30f38:	e59d0018 	ldr	r0, [sp, #24]
47f30f3c:	e1a05002 	mov	r5, r2
47f30f40:	e3a02000 	mov	r2, #0
47f30f44:	e3a0c68f 	mov	r12, #149946368	@ 0x8f00000
47f30f48:	e1500002 	cmp	r0, r2
47f30f4c:	e1a06001 	mov	r6, r1
47f30f50:	e1a09003 	mov	r9, r3
47f30f54:	e3a01001 	mov	r1, #1
47f30f58:	e3a03005 	mov	r3, #5
47f30f5c:	e58c1004 	str	r1, [r12, #4]
47f30f60:	e59f4064 	ldr	r4, [pc, #100]	@ 0x47f30fcc
47f30f64:	e58c2154 	str	r2, [r12, #340]	@ 0x154
47f30f68:	e58c3104 	str	r3, [r12, #260]	@ 0x104
47f30f6c:	158c200c 	strne	r2, [r12, #12]
47f30f70:	1a000004 	bne	0x47f30f88
47f30f74:	e58c100c 	str	r1, [r12, #12]
47f30f78:	e5943040 	ldr	r3, [r4, #64]	@ 0x40
47f30f7c:	e3530000 	cmp	r3, #0
47f30f80:	0afffffc 	beq	0x47f30f78
47f30f84:	ea000004 	b	0x47f30f9c
47f30f88:	e5943040 	ldr	r3, [r4, #64]	@ 0x40
47f30f8c:	e3530000 	cmp	r3, #0
47f30f90:	0afffffc 	beq	0x47f30f88
47f30f94:	e3a01080 	mov	r1, #128	@ 0x80
47f30f98:	ebffff0b 	bl	0x47f30bcc
47f30f9c:	e1a00009 	mov	r0, r9
47f30fa0:	e3a0468f 	mov	r4, #149946368	@ 0x8f00000
47f30fa4:	ebffff14 	bl	0x47f30bfc
47f30fa8:	e3a03001 	mov	r3, #1
47f30fac:	e1a00007 	mov	r0, r7
47f30fb0:	e5843154 	str	r3, [r4, #340]	@ 0x154
47f30fb4:	e1a01006 	mov	r1, r6
47f30fb8:	e1a02005 	mov	r2, r5
47f30fbc:	ebffff2c 	bl	0x47f30c74
47f30fc0:	e3a00000 	mov	r0, #0
47f30fc4:	e5840154 	str	r0, [r4, #340]	@ 0x154
47f30fc8:	e8bd82f0 	pop	{r4, r5, r6, r7, r9, pc}
47f30fcc:	9a107000 	bls	0x4834cfd4
47f30fd0:	e92d4ef3 	push	{r0, r1, r4, r5, r6, r7, r9, r10, r11, lr}
47f30fd4:	e1a05003 	mov	r5, r3
47f30fd8:	e59f3164 	ldr	r3, [pc, #356]	@ 0x47f31144
47f30fdc:	e1a06001 	mov	r6, r1
47f30fe0:	e59f1160 	ldr	r1, [pc, #352]	@ 0x47f31148
47f30fe4:	e3a02004 	mov	r2, #4
47f30fe8:	e59d9028 	ldr	r9, [sp, #40]	@ 0x28
47f30fec:	e3a0c000 	mov	r12, #0
47f30ff0:	e58d3004 	str	r3, [sp, #4]
47f30ff4:	e3a0368f 	mov	r3, #149946368	@ 0x8f00000
47f30ff8:	e5832004 	str	r2, [r3, #4]
47f30ffc:	e2833c05 	add	r3, r3, #1280	@ 0x500
47f31000:	e483c004 	str	r12, [r3], #4
47f31004:	e1530001 	cmp	r3, r1
47f31008:	e3a02000 	mov	r2, #0
47f3100c:	1afffffb 	bne	0x47f31000
47f31010:	e285701f 	add	r7, r5, #31
47f31014:	e3a0368f 	mov	r3, #149946368	@ 0x8f00000
47f31018:	e5832418 	str	r2, [r3, #1048]	@ 0x418
47f3101c:	e3a0c001 	mov	r12, #1
47f31020:	e1a072a7 	lsr	r7, r7, #5
47f31024:	e5832414 	str	r2, [r3, #1044]	@ 0x414
47f31028:	e3a02006 	mov	r2, #6
47f3102c:	e5832424 	str	r2, [r3, #1060]	@ 0x424
47f31030:	e2472107 	sub	r2, r7, #-1073741823	@ 0xc0000001
47f31034:	e1a0400c 	mov	r4, r12
47f31038:	e3a0a002 	mov	r10, #2
47f3103c:	e7991102 	ldr	r1, [r9, r2, lsl #2]
47f31040:	e583141c 	str	r1, [r3, #1052]	@ 0x41c
47f31044:	e1a0300c 	mov	r3, r12
47f31048:	e1a0231a 	lsl	r2, r10, r3
47f3104c:	e1a0e314 	lsl	lr, r4, r3
47f31050:	e242b001 	sub	r11, r2, #1
47f31054:	e2833001 	add	r3, r3, #1
47f31058:	e0020c91 	mul	r2, r1, r12
47f3105c:	e002200b 	and	r2, r2, r11
47f31060:	e15e0002 	cmp	lr, r2
47f31064:	308cc00e 	addcc	r12, r12, lr
47f31068:	e3530020 	cmp	r3, #32
47f3106c:	1afffff5 	bne	0x47f31048
47f31070:	e3a0468f 	mov	r4, #149946368	@ 0x8f00000
47f31074:	e26cc000 	rsb	r12, r12, #0
47f31078:	e59f10cc 	ldr	r1, [pc, #204]	@ 0x47f3114c
47f3107c:	e1a02007 	mov	r2, r7
47f31080:	e584c420 	str	r12, [r4, #1056]	@ 0x420
47f31084:	ebfffee6 	bl	0x47f30c24
47f31088:	e28d0004 	add	r0, sp, #4
47f3108c:	e59f10bc 	ldr	r1, [pc, #188]	@ 0x47f31150
47f31090:	e3a02001 	mov	r2, #1
47f31094:	ebfffee2 	bl	0x47f30c24
47f31098:	e1a00009 	mov	r0, r9
47f3109c:	e59f10b0 	ldr	r1, [pc, #176]	@ 0x47f31154
47f310a0:	e1a02007 	mov	r2, r7
47f310a4:	ebfffede 	bl	0x47f30c24
47f310a8:	e5993000 	ldr	r3, [r9]
47f310ac:	e3530000 	cmp	r3, #0
47f310b0:	e3a03000 	mov	r3, #0
47f310b4:	a2455002 	subge	r5, r5, #2
47f310b8:	b2455001 	sublt	r5, r5, #1
47f310bc:	e5845408 	str	r5, [r4, #1032]	@ 0x408
47f310c0:	e3a0568f 	mov	r5, #149946368	@ 0x8f00000
47f310c4:	e584340c 	str	r3, [r4, #1036]	@ 0x40c
47f310c8:	e3a03001 	mov	r3, #1
47f310cc:	e5843404 	str	r3, [r4, #1028]	@ 0x404
47f310d0:	e59f4080 	ldr	r4, [pc, #128]	@ 0x47f31158
47f310d4:	e5953410 	ldr	r3, [r5, #1040]	@ 0x410
47f310d8:	e3130001 	tst	r3, #1
47f310dc:	1a000007 	bne	0x47f31100
47f310e0:	e3a0000a 	mov	r0, #10
47f310e4:	ebffd602 	bl	0x47f268f4
47f310e8:	e2544001 	subs	r4, r4, #1
47f310ec:	1afffff8 	bne	0x47f310d4
47f310f0:	e59f0064 	ldr	r0, [pc, #100]	@ 0x47f3115c
47f310f4:	ebff6517 	bl	0x47f0a558
47f310f8:	e3a00001 	mov	r0, #1
47f310fc:	ea00000e 	b	0x47f3113c
47f31100:	e3a0368f 	mov	r3, #149946368	@ 0x8f00000
47f31104:	e3a02001 	mov	r2, #1
47f31108:	e5832410 	str	r2, [r3, #1040]	@ 0x410
47f3110c:	e3a03000 	mov	r3, #0
47f31110:	e59f2048 	ldr	r2, [pc, #72]	@ 0x47f31160
47f31114:	e1a01103 	lsl	r1, r3, #2
47f31118:	e0612002 	rsb	r2, r1, r2
47f3111c:	e5922000 	ldr	r2, [r2]
47f31120:	e7862103 	str	r2, [r6, r3, lsl #2]
47f31124:	e2833001 	add	r3, r3, #1
47f31128:	e3530008 	cmp	r3, #8
47f3112c:	1afffff7 	bne	0x47f31110
47f31130:	e3a0368f 	mov	r3, #149946368	@ 0x8f00000
47f31134:	e3a00000 	mov	r0, #0
47f31138:	e5830404 	str	r0, [r3, #1028]	@ 0x404
47f3113c:	e28dd008 	add	sp, sp, #8
47f31140:	e8bd8ef0 	pop	{r4, r5, r6, r7, r9, r10, r11, pc}
47f31144:	00010001 	andeq	r0, r1, r1
47f31148:	08f00900 	ldmeq	r0!, {r8, r11}^
47f3114c:	08f00500 	ldmeq	r0!, {r8, r10}^
47f31150:	08f00600 	ldmeq	r0!, {r9, r10}^
47f31154:	08f00700 	ldmeq	r0!, {r8, r9, r10}^
47f31158:	000186a1 	andeq	r8, r1, r1, lsr #13
47f3115c:	47f4439d 			@ <UNDEFINED> instruction: 0x47f4439d
47f31160:	08f0091c 	ldmeq	r0!, {r2, r3, r4, r8, r11}^
47f31164:	e3a0368f 	mov	r3, #149946368	@ 0x8f00000
47f31168:	e3a0c001 	mov	r12, #1
47f3116c:	e92d4070 	push	{r4, r5, r6, lr}
47f31170:	e1a04001 	mov	r4, r1
47f31174:	e3a01002 	mov	r1, #2
47f31178:	e5831004 	str	r1, [r3, #4]
47f3117c:	e583c304 	str	r12, [r3, #772]	@ 0x304
47f31180:	e1a01182 	lsl	r1, r2, #3
47f31184:	e583132c 	str	r1, [r3, #812]	@ 0x32c
47f31188:	e1a01ea2 	lsr	r1, r2, #29
47f3118c:	e2822003 	add	r2, r2, #3
47f31190:	e5831328 	str	r1, [r3, #808]	@ 0x328
47f31194:	e3c22003 	bic	r2, r2, #3
47f31198:	e3a01000 	mov	r1, #0
47f3119c:	e0802002 	add	r2, r0, r2
47f311a0:	e5831324 	str	r1, [r3, #804]	@ 0x324
47f311a4:	e5831320 	str	r1, [r3, #800]	@ 0x320
47f311a8:	e583c308 	str	r12, [r3, #776]	@ 0x308
47f311ac:	e5831314 	str	r1, [r3, #788]	@ 0x314
47f311b0:	e1500002 	cmp	r0, r2
47f311b4:	14901004 	ldrne	r1, [r0], #4
47f311b8:	15831310 	strne	r1, [r3, #784]	@ 0x310
47f311bc:	1afffffb 	bne	0x47f311b0
47f311c0:	e59f5058 	ldr	r5, [pc, #88]	@ 0x47f31220
47f311c4:	e3a0668f 	mov	r6, #149946368	@ 0x8f00000
47f311c8:	e5960308 	ldr	r0, [r6, #776]	@ 0x308
47f311cc:	e3a0368f 	mov	r3, #149946368	@ 0x8f00000
47f311d0:	e2100001 	ands	r0, r0, #1
47f311d4:	0a000007 	beq	0x47f311f8
47f311d8:	e3a0000a 	mov	r0, #10
47f311dc:	ebffd5c4 	bl	0x47f268f4
47f311e0:	e2555001 	subs	r5, r5, #1
47f311e4:	1afffff7 	bne	0x47f311c8
47f311e8:	e59f0034 	ldr	r0, [pc, #52]	@ 0x47f31224
47f311ec:	ebff64d9 	bl	0x47f0a558
47f311f0:	e3a00001 	mov	r0, #1
47f311f4:	e8bd8070 	pop	{r4, r5, r6, pc}
47f311f8:	e5932360 	ldr	r2, [r3, #864]	@ 0x360
47f311fc:	e5842000 	str	r2, [r4]
47f31200:	e5932364 	ldr	r2, [r3, #868]	@ 0x364
47f31204:	e5842004 	str	r2, [r4, #4]
47f31208:	e5932368 	ldr	r2, [r3, #872]	@ 0x368
47f3120c:	e5842008 	str	r2, [r4, #8]
47f31210:	e593236c 	ldr	r2, [r3, #876]	@ 0x36c
47f31214:	e584200c 	str	r2, [r4, #12]
47f31218:	e5830304 	str	r0, [r3, #772]	@ 0x304
47f3121c:	e8bd8070 	pop	{r4, r5, r6, pc}
47f31220:	000186a1 	andeq	r8, r1, r1, lsr #13
47f31224:	47f443aa 	ldrbmi	r4, [r4, r10, lsr #7]!
47f31228:	e3a0368f 	mov	r3, #149946368	@ 0x8f00000
47f3122c:	e3a0c001 	mov	r12, #1
47f31230:	e92d4070 	push	{r4, r5, r6, lr}
47f31234:	e1a04001 	mov	r4, r1
47f31238:	e3a01002 	mov	r1, #2
47f3123c:	e5831004 	str	r1, [r3, #4]
47f31240:	e3a01031 	mov	r1, #49	@ 0x31
47f31244:	e5831304 	str	r1, [r3, #772]	@ 0x304
47f31248:	e1a01182 	lsl	r1, r2, #3
47f3124c:	e583132c 	str	r1, [r3, #812]	@ 0x32c
47f31250:	e1a01ea2 	lsr	r1, r2, #29
47f31254:	e2822003 	add	r2, r2, #3
47f31258:	e3c22003 	bic	r2, r2, #3
47f3125c:	e5831328 	str	r1, [r3, #808]	@ 0x328
47f31260:	e0802002 	add	r2, r0, r2
47f31264:	e3a01000 	mov	r1, #0
47f31268:	e5831324 	str	r1, [r3, #804]	@ 0x324
47f3126c:	e5831320 	str	r1, [r3, #800]	@ 0x320
47f31270:	e583c308 	str	r12, [r3, #776]	@ 0x308
47f31274:	e5831314 	str	r1, [r3, #788]	@ 0x314
47f31278:	e1500002 	cmp	r0, r2
47f3127c:	14901004 	ldrne	r1, [r0], #4
47f31280:	15831310 	strne	r1, [r3, #784]	@ 0x310
47f31284:	1afffffb 	bne	0x47f31278
47f31288:	e59f5058 	ldr	r5, [pc, #88]	@ 0x47f312e8
47f3128c:	e3a0668f 	mov	r6, #149946368	@ 0x8f00000
47f31290:	e5963308 	ldr	r3, [r6, #776]	@ 0x308
47f31294:	e3130001 	tst	r3, #1
47f31298:	0a000007 	beq	0x47f312bc
47f3129c:	e3a0000a 	mov	r0, #10
47f312a0:	ebffd593 	bl	0x47f268f4
47f312a4:	e2555001 	subs	r5, r5, #1
47f312a8:	1afffff8 	bne	0x47f31290
47f312ac:	e59f0038 	ldr	r0, [pc, #56]	@ 0x47f312ec
47f312b0:	ebff64a8 	bl	0x47f0a558
47f312b4:	e3a00001 	mov	r0, #1
47f312b8:	e8bd8070 	pop	{r4, r5, r6, pc}
47f312bc:	e59f302c 	ldr	r3, [pc, #44]	@ 0x47f312f0
47f312c0:	e2441004 	sub	r1, r4, #4
47f312c4:	e59f2028 	ldr	r2, [pc, #40]	@ 0x47f312f4
47f312c8:	e4930004 	ldr	r0, [r3], #4
47f312cc:	e1530002 	cmp	r3, r2
47f312d0:	e5a10004 	str	r0, [r1, #4]!
47f312d4:	1afffffb 	bne	0x47f312c8
47f312d8:	e3a0368f 	mov	r3, #149946368	@ 0x8f00000
47f312dc:	e3a00000 	mov	r0, #0
47f312e0:	e5830304 	str	r0, [r3, #772]	@ 0x304
47f312e4:	e8bd8070 	pop	{r4, r5, r6, pc}
47f312e8:	000186a1 	andeq	r8, r1, r1, lsr #13
47f312ec:	47f443aa 	ldrbmi	r4, [r4, r10, lsr #7]!
47f312f0:	08f00350 	ldmeq	r0!, {r4, r6, r8, r9}^
47f312f4:	08f00370 	ldmeq	r0!, {r4, r5, r6, r8, r9}^
47f312f8:	e3a03000 	mov	r3, #0
47f312fc:	e52de004 	push	{lr}		@ (str lr, [sp, #-4]!)
47f31300:	e1530002 	cmp	r3, r2
47f31304:	0a000005 	beq	0x47f31320
47f31308:	e790e103 	ldr	lr, [r0, r3, lsl #2]
47f3130c:	e791c103 	ldr	r12, [r1, r3, lsl #2]
47f31310:	e15e000c 	cmp	lr, r12
47f31314:	1a000003 	bne	0x47f31328
47f31318:	e2833001 	add	r3, r3, #1
47f3131c:	eafffff7 	b	0x47f31300
47f31320:	e3a00000 	mov	r0, #0
47f31324:	e49df004 	pop	{pc}		@ (ldr pc, [sp], #4)
47f31328:	e3a00001 	mov	r0, #1
47f3132c:	e49df004 	pop	{pc}		@ (ldr pc, [sp], #4)
47f31330:	e59f303c 	ldr	r3, [pc, #60]	@ 0x47f31374
47f31334:	e5931000 	ldr	r1, [r3]
47f31338:	e59f2038 	ldr	r2, [pc, #56]	@ 0x47f31378
47f3133c:	e1510002 	cmp	r1, r2
47f31340:	0a000006 	beq	0x47f31360
47f31344:	e5931000 	ldr	r1, [r3]
47f31348:	e59f302c 	ldr	r3, [pc, #44]	@ 0x47f3137c
47f3134c:	e59f202c 	ldr	r2, [pc, #44]	@ 0x47f31380
47f31350:	e1510003 	cmp	r1, r3
47f31354:	01a03002 	moveq	r3, r2
47f31358:	13a03000 	movne	r3, #0
47f3135c:	ea000000 	b	0x47f31364
47f31360:	e59f301c 	ldr	r3, [pc, #28]	@ 0x47f31384
47f31364:	e5900010 	ldr	r0, [r0, #16]
47f31368:	e0530000 	subs	r0, r3, r0
47f3136c:	13a00001 	movne	r0, #1
47f31370:	e12fff1e 	bx	lr
47f31374:	92040000 	andls	r0, r4, #0
47f31378:	27912710 			@ <UNDEFINED> instruction: 0x27912710
47f3137c:	27912810 			@ <UNDEFINED> instruction: 0x27912810
47f31380:	73383231 	teqvc	r8, #268435459	@ 0x10000003
47f31384:	73373231 	teqvc	r7, #268435459	@ 0x10000003
47f31388:	e5d030a6 	ldrb	r3, [r0, #166]	@ 0xa6
47f3138c:	e3530034 	cmp	r3, #52	@ 0x34
47f31390:	0a000003 	beq	0x47f313a4
47f31394:	e3530036 	cmp	r3, #54	@ 0x36
47f31398:	03a00c06 	moveq	r0, #1536	@ 0x600
47f3139c:	13a00b02 	movne	r0, #2048	@ 0x800
47f313a0:	e12fff1e 	bx	lr
47f313a4:	e3a00b01 	mov	r0, #1024	@ 0x400
47f313a8:	e12fff1e 	bx	lr
47f313ac:	e59f3008 	ldr	r3, [pc, #8]	@ 0x47f313bc
47f313b0:	e593001c 	ldr	r0, [r3, #28]
47f313b4:	e2000001 	and	r0, r0, #1
47f313b8:	e12fff1e 	bx	lr
47f313bc:	9a107000 	bls	0x4834d3c4
47f313c0:	e59f2018 	ldr	r2, [pc, #24]	@ 0x47f313e0
47f313c4:	e5923040 	ldr	r3, [r2, #64]	@ 0x40
47f313c8:	e3530000 	cmp	r3, #0
47f313cc:	0afffffc 	beq	0x47f313c4
47f313d0:	e59f3008 	ldr	r3, [pc, #8]	@ 0x47f313e0
47f313d4:	e593001c 	ldr	r0, [r3, #28]
47f313d8:	e2000001 	and	r0, r0, #1
47f313dc:	e12fff1e 	bx	lr
47f313e0:	9a107000 	bls	0x4834d3e8
47f313e4:	e92d4eff 	push	{r0, r1, r2, r3, r4, r5, r6, r7, r9, r10, r11, lr}
47f313e8:	e3a03b02 	mov	r3, #2048	@ 0x800
47f313ec:	e99000e0 	ldmib	r0, {r5, r6, r7}
47f313f0:	e1a04000 	mov	r4, r0
47f313f4:	e59f9534 	ldr	r9, [pc, #1332]	@ 0x47f31930
47f313f8:	e3a02010 	mov	r2, #16
47f313fc:	e5803014 	str	r3, [r0, #20]
47f31400:	e59f152c 	ldr	r1, [pc, #1324]	@ 0x47f31934
47f31404:	e5809018 	str	r9, [r0, #24]
47f31408:	e1a00005 	mov	r0, r5
47f3140c:	ebffff85 	bl	0x47f31228
47f31410:	e3500000 	cmp	r0, #0
47f31414:	0a000003 	beq	0x47f31428
47f31418:	e59f0518 	ldr	r0, [pc, #1304]	@ 0x47f31938
47f3141c:	e3a0b001 	mov	r11, #1
47f31420:	ebff644c 	bl	0x47f0a558
47f31424:	ea00013e 	b	0x47f31924
47f31428:	e5d43001 	ldrb	r3, [r4, #1]
47f3142c:	e3530000 	cmp	r3, #0
47f31430:	05943028 	ldreq	r3, [r4, #40]	@ 0x28
47f31434:	02833f71 	addeq	r3, r3, #452	@ 0x1c4
47f31438:	05843024 	streq	r3, [r4, #36]	@ 0x24
47f3143c:	0a00000e 	beq	0x47f3147c
47f31440:	e59f34f4 	ldr	r3, [pc, #1268]	@ 0x47f3193c
47f31444:	e5931000 	ldr	r1, [r3]
47f31448:	e59f24f0 	ldr	r2, [pc, #1264]	@ 0x47f31940
47f3144c:	e1510002 	cmp	r1, r2
47f31450:	02899010 	addeq	r9, r9, #16
47f31454:	0a000004 	beq	0x47f3146c
47f31458:	e5932000 	ldr	r2, [r3]
47f3145c:	e59f34e0 	ldr	r3, [pc, #1248]	@ 0x47f31944
47f31460:	e1520003 	cmp	r2, r3
47f31464:	1a000002 	bne	0x47f31474
47f31468:	e2899e11 	add	r9, r9, #272	@ 0x110
47f3146c:	e5849024 	str	r9, [r4, #36]	@ 0x24
47f31470:	ea000001 	b	0x47f3147c
47f31474:	e59f04cc 	ldr	r0, [pc, #1228]	@ 0x47f31948
47f31478:	ea00000a 	b	0x47f314a8
47f3147c:	e5943024 	ldr	r3, [r4, #36]	@ 0x24
47f31480:	e2850b01 	add	r0, r5, #1024	@ 0x400
47f31484:	e59f14c0 	ldr	r1, [pc, #1216]	@ 0x47f3194c
47f31488:	e3a02000 	mov	r2, #0
47f3148c:	e584001c 	str	r0, [r4, #28]
47f31490:	e58d3000 	str	r3, [sp]
47f31494:	e5943014 	ldr	r3, [r4, #20]
47f31498:	ebfffecc 	bl	0x47f30fd0
47f3149c:	e3500000 	cmp	r0, #0
47f314a0:	0a000003 	beq	0x47f314b4
47f314a4:	e59f04a4 	ldr	r0, [pc, #1188]	@ 0x47f31950
47f314a8:	ebff642a 	bl	0x47f0a558
47f314ac:	e3a0b002 	mov	r11, #2
47f314b0:	ea00011b 	b	0x47f31924
47f314b4:	e59f0478 	ldr	r0, [pc, #1144]	@ 0x47f31934
47f314b8:	e3a02008 	mov	r2, #8
47f314bc:	e2801040 	add	r1, r0, #64	@ 0x40
47f314c0:	ebffff8c 	bl	0x47f312f8
47f314c4:	e2509000 	subs	r9, r0, #0
47f314c8:	0a000003 	beq	0x47f314dc
47f314cc:	e59f0480 	ldr	r0, [pc, #1152]	@ 0x47f31954
47f314d0:	e3a0b003 	mov	r11, #3
47f314d4:	ebff641f 	bl	0x47f0a558
47f314d8:	ea000111 	b	0x47f31924
47f314dc:	e1a01009 	mov	r1, r9
47f314e0:	e3a02020 	mov	r2, #32
47f314e4:	e59f0448 	ldr	r0, [pc, #1096]	@ 0x47f31934
47f314e8:	ebffd45d 	bl	0x47f26664
47f314ec:	e3a010ff 	mov	r1, #255	@ 0xff
47f314f0:	e3a02020 	mov	r2, #32
47f314f4:	e59f0450 	ldr	r0, [pc, #1104]	@ 0x47f3194c
47f314f8:	ebffd459 	bl	0x47f26664
47f314fc:	e5d43000 	ldrb	r3, [r4]
47f31500:	e1a00005 	mov	r0, r5
47f31504:	e1a01005 	mov	r1, r5
47f31508:	e3530000 	cmp	r3, #0
47f3150c:	15849020 	strne	r9, [r4, #32]
47f31510:	e3a02010 	mov	r2, #16
47f31514:	05943028 	ldreq	r3, [r4, #40]	@ 0x28
47f31518:	02833fb1 	addeq	r3, r3, #708	@ 0x2c4
47f3151c:	05843020 	streq	r3, [r4, #32]
47f31520:	e5943020 	ldr	r3, [r4, #32]
47f31524:	e58d3000 	str	r3, [sp]
47f31528:	e5943018 	ldr	r3, [r4, #24]
47f3152c:	ebfffe7f 	bl	0x47f30f30
47f31530:	e3500000 	cmp	r0, #0
47f31534:	0a000003 	beq	0x47f31548
47f31538:	e59f0418 	ldr	r0, [pc, #1048]	@ 0x47f31958
47f3153c:	e3a0b004 	mov	r11, #4
47f31540:	ebff6404 	bl	0x47f0a558
47f31544:	ea0000f6 	b	0x47f31924
47f31548:	e2859080 	add	r9, r5, #128	@ 0x80
47f3154c:	e5845020 	str	r5, [r4, #32]
47f31550:	e3a02d0e 	mov	r2, #896	@ 0x380
47f31554:	e58d5000 	str	r5, [sp]
47f31558:	e1a01009 	mov	r1, r9
47f3155c:	e1a00009 	mov	r0, r9
47f31560:	e5943018 	ldr	r3, [r4, #24]
47f31564:	ebfffe71 	bl	0x47f30f30
47f31568:	e2501000 	subs	r1, r0, #0
47f3156c:	0a000003 	beq	0x47f31580
47f31570:	e59f03e4 	ldr	r0, [pc, #996]	@ 0x47f3195c
47f31574:	e3a0b005 	mov	r11, #5
47f31578:	ebff63f6 	bl	0x47f0a558
47f3157c:	ea0000e8 	b	0x47f31924
47f31580:	e285a0b4 	add	r10, r5, #180	@ 0xb4
47f31584:	e3a02010 	mov	r2, #16
47f31588:	e1a00005 	mov	r0, r5
47f3158c:	ebffd434 	bl	0x47f26664
47f31590:	e1a0000a 	mov	r0, r10
47f31594:	e59f1398 	ldr	r1, [pc, #920]	@ 0x47f31934
47f31598:	e3a02c01 	mov	r2, #256	@ 0x100
47f3159c:	ebffff21 	bl	0x47f31228
47f315a0:	e3500000 	cmp	r0, #0
47f315a4:	0a000003 	beq	0x47f315b8
47f315a8:	e59f03b0 	ldr	r0, [pc, #944]	@ 0x47f31960
47f315ac:	e3a0b006 	mov	r11, #6
47f315b0:	ebff63e8 	bl	0x47f0a558
47f315b4:	ea0000da 	b	0x47f31924
47f315b8:	e5d43001 	ldrb	r3, [r4, #1]
47f315bc:	e3530000 	cmp	r3, #0
47f315c0:	05943028 	ldreq	r3, [r4, #40]	@ 0x28
47f315c4:	02833f71 	addeq	r3, r3, #452	@ 0x1c4
47f315c8:	0a00000a 	beq	0x47f315f8
47f315cc:	e59f3368 	ldr	r3, [pc, #872]	@ 0x47f3193c
47f315d0:	e5931000 	ldr	r1, [r3]
47f315d4:	e59f2364 	ldr	r2, [pc, #868]	@ 0x47f31940
47f315d8:	e1510002 	cmp	r1, r2
47f315dc:	059f3380 	ldreq	r3, [pc, #896]	@ 0x47f31964
47f315e0:	0a000004 	beq	0x47f315f8
47f315e4:	e5932000 	ldr	r2, [r3]
47f315e8:	e59f3354 	ldr	r3, [pc, #852]	@ 0x47f31944
47f315ec:	e1520003 	cmp	r2, r3
47f315f0:	1affff9f 	bne	0x47f31474
47f315f4:	e59f336c 	ldr	r3, [pc, #876]	@ 0x47f31968
47f315f8:	e5843024 	str	r3, [r4, #36]	@ 0x24
47f315fc:	e2850c05 	add	r0, r5, #1280	@ 0x500
47f31600:	e5943024 	ldr	r3, [r4, #36]	@ 0x24
47f31604:	e3a02000 	mov	r2, #0
47f31608:	e584001c 	str	r0, [r4, #28]
47f3160c:	e59f1338 	ldr	r1, [pc, #824]	@ 0x47f3194c
47f31610:	e58d3000 	str	r3, [sp]
47f31614:	e5943014 	ldr	r3, [r4, #20]
47f31618:	ebfffe6c 	bl	0x47f30fd0
47f3161c:	e3500000 	cmp	r0, #0
47f31620:	0a000003 	beq	0x47f31634
47f31624:	e59f0340 	ldr	r0, [pc, #832]	@ 0x47f3196c
47f31628:	e3a0b007 	mov	r11, #7
47f3162c:	ebff63c9 	bl	0x47f0a558
47f31630:	ea0000bb 	b	0x47f31924
47f31634:	e59f02f8 	ldr	r0, [pc, #760]	@ 0x47f31934
47f31638:	e3a02008 	mov	r2, #8
47f3163c:	e2801040 	add	r1, r0, #64	@ 0x40
47f31640:	ebffff2c 	bl	0x47f312f8
47f31644:	e2501000 	subs	r1, r0, #0
47f31648:	0a000003 	beq	0x47f3165c
47f3164c:	e59f031c 	ldr	r0, [pc, #796]	@ 0x47f31970
47f31650:	e3a0b008 	mov	r11, #8
47f31654:	ebff63bf 	bl	0x47f0a558
47f31658:	ea0000b1 	b	0x47f31924
47f3165c:	e3a02020 	mov	r2, #32
47f31660:	e59f02cc 	ldr	r0, [pc, #716]	@ 0x47f31934
47f31664:	ebffd3fe 	bl	0x47f26664
47f31668:	e3a010ff 	mov	r1, #255	@ 0xff
47f3166c:	e3a02020 	mov	r2, #32
47f31670:	e59f02d4 	ldr	r0, [pc, #724]	@ 0x47f3194c
47f31674:	ebffd3fa 	bl	0x47f26664
47f31678:	e1a00009 	mov	r0, r9
47f3167c:	e59f12b0 	ldr	r1, [pc, #688]	@ 0x47f31934
47f31680:	e3a02d0e 	mov	r2, #896	@ 0x380
47f31684:	ebfffee7 	bl	0x47f31228
47f31688:	e2509000 	subs	r9, r0, #0
47f3168c:	0a000003 	beq	0x47f316a0
47f31690:	e59f02dc 	ldr	r0, [pc, #732]	@ 0x47f31974
47f31694:	e3a0b009 	mov	r11, #9
47f31698:	ebff63ae 	bl	0x47f0a558
47f3169c:	ea0000a0 	b	0x47f31924
47f316a0:	e1a00005 	mov	r0, r5
47f316a4:	ebffff37 	bl	0x47f31388
47f316a8:	e584a024 	str	r10, [r4, #36]	@ 0x24
47f316ac:	e59f1298 	ldr	r1, [pc, #664]	@ 0x47f3194c
47f316b0:	e1a02009 	mov	r2, r9
47f316b4:	e5840014 	str	r0, [r4, #20]
47f316b8:	e1a03000 	mov	r3, r0
47f316bc:	e2850c06 	add	r0, r5, #1536	@ 0x600
47f316c0:	e584001c 	str	r0, [r4, #28]
47f316c4:	e58da000 	str	r10, [sp]
47f316c8:	ebfffe40 	bl	0x47f30fd0
47f316cc:	e3500000 	cmp	r0, #0
47f316d0:	0a000003 	beq	0x47f316e4
47f316d4:	e59f029c 	ldr	r0, [pc, #668]	@ 0x47f31978
47f316d8:	e3a0b00a 	mov	r11, #10
47f316dc:	ebff639d 	bl	0x47f0a558
47f316e0:	ea00008f 	b	0x47f31924
47f316e4:	e59f0248 	ldr	r0, [pc, #584]	@ 0x47f31934
47f316e8:	e3a02008 	mov	r2, #8
47f316ec:	e2801040 	add	r1, r0, #64	@ 0x40
47f316f0:	ebffff00 	bl	0x47f312f8
47f316f4:	e2501000 	subs	r1, r0, #0
47f316f8:	0a000003 	beq	0x47f3170c
47f316fc:	e59f0278 	ldr	r0, [pc, #632]	@ 0x47f3197c
47f31700:	e3a0b00b 	mov	r11, #11
47f31704:	ebff6393 	bl	0x47f0a558
47f31708:	ea000085 	b	0x47f31924
47f3170c:	e3a02020 	mov	r2, #32
47f31710:	e59f021c 	ldr	r0, [pc, #540]	@ 0x47f31934
47f31714:	ebffd3d2 	bl	0x47f26664
47f31718:	e3a010ff 	mov	r1, #255	@ 0xff
47f3171c:	e3a02020 	mov	r2, #32
47f31720:	e59f0224 	ldr	r0, [pc, #548]	@ 0x47f3194c
47f31724:	ebffd3ce 	bl	0x47f26664
47f31728:	e2853fbd 	add	r3, r5, #756	@ 0x2f4
47f3172c:	e1a00006 	mov	r0, r6
47f31730:	e59f11fc 	ldr	r1, [pc, #508]	@ 0x47f31934
47f31734:	e1d320b0 	ldrh	r2, [r3]
47f31738:	e58d300c 	str	r3, [sp, #12]
47f3173c:	e3520000 	cmp	r2, #0
47f31740:	11a02502 	lslne	r2, r2, #10
47f31744:	059520b0 	ldreq	r2, [r5, #176]	@ 0xb0
47f31748:	ebfffeb6 	bl	0x47f31228
47f3174c:	e3500000 	cmp	r0, #0
47f31750:	e1a09000 	mov	r9, r0
47f31754:	0a000003 	beq	0x47f31768
47f31758:	e59f0220 	ldr	r0, [pc, #544]	@ 0x47f31980
47f3175c:	e3a0b00c 	mov	r11, #12
47f31760:	ebff637c 	bl	0x47f0a558
47f31764:	ea00006e 	b	0x47f31924
47f31768:	e1a00005 	mov	r0, r5
47f3176c:	ebffff05 	bl	0x47f31388
47f31770:	e584a024 	str	r10, [r4, #36]	@ 0x24
47f31774:	e59f11d0 	ldr	r1, [pc, #464]	@ 0x47f3194c
47f31778:	e1a02009 	mov	r2, r9
47f3177c:	e5840014 	str	r0, [r4, #20]
47f31780:	e1a03000 	mov	r3, r0
47f31784:	e2850c07 	add	r0, r5, #1792	@ 0x700
47f31788:	e584001c 	str	r0, [r4, #28]
47f3178c:	e58da000 	str	r10, [sp]
47f31790:	ebfffe0e 	bl	0x47f30fd0
47f31794:	e3500000 	cmp	r0, #0
47f31798:	0a000003 	beq	0x47f317ac
47f3179c:	e59f01e0 	ldr	r0, [pc, #480]	@ 0x47f31984
47f317a0:	e3a0b00d 	mov	r11, #13
47f317a4:	ebff636b 	bl	0x47f0a558
47f317a8:	ea00005d 	b	0x47f31924
47f317ac:	e59f0180 	ldr	r0, [pc, #384]	@ 0x47f31934
47f317b0:	e3a02008 	mov	r2, #8
47f317b4:	e2801040 	add	r1, r0, #64	@ 0x40
47f317b8:	ebfffece 	bl	0x47f312f8
47f317bc:	e250b000 	subs	r11, r0, #0
47f317c0:	0a000003 	beq	0x47f317d4
47f317c4:	e59f01bc 	ldr	r0, [pc, #444]	@ 0x47f31988
47f317c8:	e3a0b00e 	mov	r11, #14
47f317cc:	ebff6361 	bl	0x47f0a558
47f317d0:	ea000053 	b	0x47f31924
47f317d4:	e1a01009 	mov	r1, r9
47f317d8:	e3a02c01 	mov	r2, #256	@ 0x100
47f317dc:	e1a0000a 	mov	r0, r10
47f317e0:	ebffd39f 	bl	0x47f26664
47f317e4:	e1a01009 	mov	r1, r9
47f317e8:	e3a02020 	mov	r2, #32
47f317ec:	e59f0140 	ldr	r0, [pc, #320]	@ 0x47f31934
47f317f0:	ebffd39b 	bl	0x47f26664
47f317f4:	e59f0150 	ldr	r0, [pc, #336]	@ 0x47f3194c
47f317f8:	e3a010ff 	mov	r1, #255	@ 0xff
47f317fc:	e3a02020 	mov	r2, #32
47f31800:	ebffd397 	bl	0x47f26664
47f31804:	e5d43002 	ldrb	r3, [r4, #2]
47f31808:	e3530000 	cmp	r3, #0
47f3180c:	1a00002e 	bne	0x47f318cc
47f31810:	e5d530a8 	ldrb	r3, [r5, #168]	@ 0xa8
47f31814:	e3530000 	cmp	r3, #0
47f31818:	0a000025 	beq	0x47f318b4
47f3181c:	e59d300c 	ldr	r3, [sp, #12]
47f31820:	e2859f6d 	add	r9, r5, #436	@ 0x1b4
47f31824:	e1a00006 	mov	r0, r6
47f31828:	e5849020 	str	r9, [r4, #32]
47f3182c:	e1a01007 	mov	r1, r7
47f31830:	e1d320b0 	ldrh	r2, [r3]
47f31834:	e58d9000 	str	r9, [sp]
47f31838:	e3520000 	cmp	r2, #0
47f3183c:	0a00000e 	beq	0x47f3187c
47f31840:	e5943018 	ldr	r3, [r4, #24]
47f31844:	e1a02502 	lsl	r2, r2, #10
47f31848:	ebfffdb8 	bl	0x47f30f30
47f3184c:	e1570006 	cmp	r7, r6
47f31850:	e1a04000 	mov	r4, r0
47f31854:	0a00000c 	beq	0x47f3188c
47f31858:	e59d300c 	ldr	r3, [sp, #12]
47f3185c:	e59520b0 	ldr	r2, [r5, #176]	@ 0xb0
47f31860:	e1d330b0 	ldrh	r3, [r3]
47f31864:	e1a01503 	lsl	r1, r3, #10
47f31868:	e0422503 	sub	r2, r2, r3, lsl #10
47f3186c:	e0870001 	add	r0, r7, r1
47f31870:	e0861001 	add	r1, r6, r1
47f31874:	ebffd39a 	bl	0x47f266e4
47f31878:	ea000003 	b	0x47f3188c
47f3187c:	e5943018 	ldr	r3, [r4, #24]
47f31880:	e59520b0 	ldr	r2, [r5, #176]	@ 0xb0
47f31884:	ebfffda9 	bl	0x47f30f30
47f31888:	e1a04000 	mov	r4, r0
47f3188c:	e1a00009 	mov	r0, r9
47f31890:	e3a01000 	mov	r1, #0
47f31894:	e3a02010 	mov	r2, #16
47f31898:	ebffd371 	bl	0x47f26664
47f3189c:	e3540000 	cmp	r4, #0
47f318a0:	0a00001f 	beq	0x47f31924
47f318a4:	e59f00e0 	ldr	r0, [pc, #224]	@ 0x47f3198c
47f318a8:	e3a0b00f 	mov	r11, #15
47f318ac:	ebff6329 	bl	0x47f0a558
47f318b0:	ea00001b 	b	0x47f31924
47f318b4:	e1570006 	cmp	r7, r6
47f318b8:	11a00007 	movne	r0, r7
47f318bc:	11a01006 	movne	r1, r6
47f318c0:	159520b0 	ldrne	r2, [r5, #176]	@ 0xb0
47f318c4:	1a000015 	bne	0x47f31920
47f318c8:	ea000015 	b	0x47f31924
47f318cc:	e5942010 	ldr	r2, [r4, #16]
47f318d0:	e3520000 	cmp	r2, #0
47f318d4:	0a000012 	beq	0x47f31924
47f318d8:	e5d530a8 	ldrb	r3, [r5, #168]	@ 0xa8
47f318dc:	e3530000 	cmp	r3, #0
47f318e0:	0a00000a 	beq	0x47f31910
47f318e4:	e2855f6d 	add	r5, r5, #436	@ 0x1b4
47f318e8:	e1a01007 	mov	r1, r7
47f318ec:	e5845020 	str	r5, [r4, #32]
47f318f0:	e1a00006 	mov	r0, r6
47f318f4:	e58d5000 	str	r5, [sp]
47f318f8:	e5943018 	ldr	r3, [r4, #24]
47f318fc:	ebfffd8b 	bl	0x47f30f30
47f31900:	e1a01009 	mov	r1, r9
47f31904:	e1a04000 	mov	r4, r0
47f31908:	e1a00005 	mov	r0, r5
47f3190c:	eaffffe0 	b	0x47f31894
47f31910:	e1570006 	cmp	r7, r6
47f31914:	0a000002 	beq	0x47f31924
47f31918:	e1a00007 	mov	r0, r7
47f3191c:	e1a01006 	mov	r1, r6
47f31920:	ebffd36f 	bl	0x47f266e4
47f31924:	e1a0000b 	mov	r0, r11
47f31928:	e28dd010 	add	sp, sp, #16
47f3192c:	e8bd8ef0 	pop	{r4, r5, r6, r7, r9, r10, r11, pc}
47f31930:	47f3a5b0 			@ <UNDEFINED> instruction: 0x47f3a5b0
47f31934:	47f621a0 	ldrbmi	r2, [r6, r0, lsr #3]!
47f31938:	47f3f0ba 			@ <UNDEFINED> instruction: 0x47f3f0ba
47f3193c:	92040000 	andls	r0, r4, #0
47f31940:	27912710 			@ <UNDEFINED> instruction: 0x27912710
47f31944:	27912810 			@ <UNDEFINED> instruction: 0x27912810
47f31948:	47f443b8 			@ <UNDEFINED> instruction: 0x47f443b8
47f3194c:	47f621e0 	ldrbmi	r2, [r6, r0, ror #3]!
47f31950:	47f3f0d1 	ubfxmi	pc, r1, #1, #20
47f31954:	47f3f0e8 	ldrbmi	pc, [r3, r8, ror #1]!	@ <UNPREDICTABLE>
47f31958:	47f3f0ff 			@ <UNDEFINED> instruction: 0x47f3f0ff
47f3195c:	47f3f116 			@ <UNDEFINED> instruction: 0x47f3f116
47f31960:	47f3f12d 	ldrbmi	pc, [r3, sp, lsr #2]!	@ <UNPREDICTABLE>
47f31964:	47f3a5c0 	ldrbmi	r10, [r3, r0, asr #11]!
47f31968:	47f3a6c0 	ldrbmi	r10, [r3, r0, asr #13]!
47f3196c:	47f3f144 	ldrbmi	pc, [r3, r4, asr #2]!	@ <UNPREDICTABLE>
47f31970:	47f3f15b 	ubfxmi	pc, r11, #2, #20
47f31974:	47f3f172 			@ <UNDEFINED> instruction: 0x47f3f172
47f31978:	47f3f189 	ldrbmi	pc, [r3, r9, lsl #3]!	@ <UNPREDICTABLE>
47f3197c:	47f3f1a1 	ldrbmi	pc, [r3, r1, lsr #3]!	@ <UNPREDICTABLE>
47f31980:	47f3f072 			@ <UNDEFINED> instruction: 0x47f3f072
47f31984:	47f3f08a 	ldrbmi	pc, [r3, r10, lsl #1]!	@ <UNPREDICTABLE>
47f31988:	47f3f0a2 	ldrbmi	pc, [r3, r2, lsr #1]!	@ <UNPREDICTABLE>
47f3198c:	47f443c8 	ldrbmi	r4, [r4, r8, asr #7]!
47f31990:	e92d46f8 	push	{r3, r4, r5, r6, r7, r9, r10, lr}
47f31994:	e1a05000 	mov	r5, r0
47f31998:	e99004c0 	ldmib	r0, {r6, r7, r10}
47f3199c:	ebfffe87 	bl	0x47f313c0
47f319a0:	e3500000 	cmp	r0, #0
47f319a4:	1a00003e 	bne	0x47f31aa4
47f319a8:	e59f0144 	ldr	r0, [pc, #324]	@ 0x47f31af4
47f319ac:	ebff62e9 	bl	0x47f0a558
47f319b0:	e1a00006 	mov	r0, r6
47f319b4:	ebfffe5d 	bl	0x47f31330
47f319b8:	e3500000 	cmp	r0, #0
47f319bc:	0a000001 	beq	0x47f319c8
47f319c0:	e3a00001 	mov	r0, #1
47f319c4:	e8bd86f8 	pop	{r3, r4, r5, r6, r7, r9, r10, pc}
47f319c8:	e2863fbd 	add	r3, r6, #756	@ 0x2f4
47f319cc:	e2864fb5 	add	r4, r6, #724	@ 0x2d4
47f319d0:	e59f1120 	ldr	r1, [pc, #288]	@ 0x47f31af8
47f319d4:	e1a00007 	mov	r0, r7
47f319d8:	e1d320b0 	ldrh	r2, [r3]
47f319dc:	e3520000 	cmp	r2, #0
47f319e0:	11a02502 	lslne	r2, r2, #10
47f319e4:	059620b0 	ldreq	r2, [r6, #176]	@ 0xb0
47f319e8:	ebfffe0e 	bl	0x47f31228
47f319ec:	e1a01004 	mov	r1, r4
47f319f0:	e3a02020 	mov	r2, #32
47f319f4:	e59f0100 	ldr	r0, [pc, #256]	@ 0x47f31afc
47f319f8:	ebffd339 	bl	0x47f266e4
47f319fc:	e59f00f4 	ldr	r0, [pc, #244]	@ 0x47f31af8
47f31a00:	e3a02008 	mov	r2, #8
47f31a04:	e2801040 	add	r1, r0, #64	@ 0x40
47f31a08:	ebfffe3a 	bl	0x47f312f8
47f31a0c:	e2509000 	subs	r9, r0, #0
47f31a10:	0a000002 	beq	0x47f31a20
47f31a14:	e59f00e4 	ldr	r0, [pc, #228]	@ 0x47f31b00
47f31a18:	ebff62ce 	bl	0x47f0a558
47f31a1c:	ea000032 	b	0x47f31aec
47f31a20:	e59f00dc 	ldr	r0, [pc, #220]	@ 0x47f31b04
47f31a24:	ebff62cb 	bl	0x47f0a558
47f31a28:	e1a00004 	mov	r0, r4
47f31a2c:	e1a01009 	mov	r1, r9
47f31a30:	e3a02020 	mov	r2, #32
47f31a34:	ebffd30a 	bl	0x47f26664
47f31a38:	e1a01009 	mov	r1, r9
47f31a3c:	e3a02020 	mov	r2, #32
47f31a40:	e59f00b0 	ldr	r0, [pc, #176]	@ 0x47f31af8
47f31a44:	ebffd306 	bl	0x47f26664
47f31a48:	e59f00ac 	ldr	r0, [pc, #172]	@ 0x47f31afc
47f31a4c:	e3a010ff 	mov	r1, #255	@ 0xff
47f31a50:	e3a02020 	mov	r2, #32
47f31a54:	ebffd302 	bl	0x47f26664
47f31a58:	e5d54002 	ldrb	r4, [r5, #2]
47f31a5c:	e3540000 	cmp	r4, #0
47f31a60:	1a000006 	bne	0x47f31a80
47f31a64:	e15a0007 	cmp	r10, r7
47f31a68:	0a000019 	beq	0x47f31ad4
47f31a6c:	e1a0000a 	mov	r0, r10
47f31a70:	e1a01007 	mov	r1, r7
47f31a74:	e5962014 	ldr	r2, [r6, #20]
47f31a78:	ebffd319 	bl	0x47f266e4
47f31a7c:	ea000014 	b	0x47f31ad4
47f31a80:	e15a0007 	cmp	r10, r7
47f31a84:	0a000014 	beq	0x47f31adc
47f31a88:	e5952010 	ldr	r2, [r5, #16]
47f31a8c:	e3520000 	cmp	r2, #0
47f31a90:	0a000013 	beq	0x47f31ae4
47f31a94:	e1a0000a 	mov	r0, r10
47f31a98:	e1a01007 	mov	r1, r7
47f31a9c:	ebffd310 	bl	0x47f266e4
47f31aa0:	ea00000d 	b	0x47f31adc
47f31aa4:	e59f005c 	ldr	r0, [pc, #92]	@ 0x47f31b08
47f31aa8:	ebff62aa 	bl	0x47f0a558
47f31aac:	e1a00006 	mov	r0, r6
47f31ab0:	ebfffe1e 	bl	0x47f31330
47f31ab4:	e3500000 	cmp	r0, #0
47f31ab8:	1affffc0 	bne	0x47f319c0
47f31abc:	e1a00005 	mov	r0, r5
47f31ac0:	ebfffe47 	bl	0x47f313e4
47f31ac4:	e2504000 	subs	r4, r0, #0
47f31ac8:	1a000007 	bne	0x47f31aec
47f31acc:	e59f0038 	ldr	r0, [pc, #56]	@ 0x47f31b0c
47f31ad0:	ebff62a0 	bl	0x47f0a558
47f31ad4:	e1a00004 	mov	r0, r4
47f31ad8:	e8bd86f8 	pop	{r3, r4, r5, r6, r7, r9, r10, pc}
47f31adc:	e1a00009 	mov	r0, r9
47f31ae0:	e8bd86f8 	pop	{r3, r4, r5, r6, r7, r9, r10, pc}
47f31ae4:	e1a00002 	mov	r0, r2
47f31ae8:	e8bd86f8 	pop	{r3, r4, r5, r6, r7, r9, r10, pc}
47f31aec:	e3e00000 	mvn	r0, #0
47f31af0:	e8bd86f8 	pop	{r3, r4, r5, r6, r7, r9, r10, pc}
47f31af4:	47f443e0 	ldrbmi	r4, [r4, r0, ror #7]!
47f31af8:	47f621a0 	ldrbmi	r2, [r6, r0, lsr #3]!
47f31afc:	47f621e0 	ldrbmi	r2, [r6, r0, ror #3]!
47f31b00:	47f443f2 			@ <UNDEFINED> instruction: 0x47f443f2
47f31b04:	47f44408 	ldrbmi	r4, [r4, r8, lsl #8]!
47f31b08:	47f443e4 	ldrbmi	r4, [r4, r4, ror #7]!
47f31b0c:	47f4441a 			@ <UNDEFINED> instruction: 0x47f4441a
47f31b10:	e1a03001 	mov	r3, r1
47f31b14:	e16f1f11 	clz	r1, r1
47f31b18:	e1a012a1 	lsr	r1, r1, #5
47f31b1c:	e3500004 	cmp	r0, #4
47f31b20:	83811001 	orrhi	r1, r1, #1
47f31b24:	e3510000 	cmp	r1, #0
47f31b28:	1a000014 	bne	0x47f31b80
47f31b2c:	e52de004 	push	{lr}		@ (str lr, [sp, #-4]!)
47f31b30:	e5d32003 	ldrb	r2, [r3, #3]
47f31b34:	e5d3c002 	ldrb	r12, [r3, #2]
47f31b38:	e59fe048 	ldr	lr, [pc, #72]	@ 0x47f31b88
47f31b3c:	e1a02802 	lsl	r2, r2, #16
47f31b40:	e1822c0c 	orr	r2, r2, r12, lsl #24
47f31b44:	e5d3c005 	ldrb	r12, [r3, #5]
47f31b48:	e182200c 	orr	r2, r2, r12
47f31b4c:	e5d3c004 	ldrb	r12, [r3, #4]
47f31b50:	e182240c 	orr	r2, r2, r12, lsl #8
47f31b54:	e3a0c008 	mov	r12, #8
47f31b58:	e10ee08c 	smlabb	lr, r12, r0, lr
47f31b5c:	e58e2000 	str	r2, [lr]
47f31b60:	e5d32000 	ldrb	r2, [r3]
47f31b64:	e5d33001 	ldrb	r3, [r3, #1]
47f31b68:	e1833c12 	orr	r3, r3, r2, lsl r12
47f31b6c:	e59f2018 	ldr	r2, [pc, #24]	@ 0x47f31b8c
47f31b70:	e10c208c 	smlabb	r12, r12, r0, r2
47f31b74:	e1a00001 	mov	r0, r1
47f31b78:	e58c3000 	str	r3, [r12]
47f31b7c:	e49df004 	pop	{pc}		@ (ldr pc, [sp], #4)
47f31b80:	e3e00000 	mvn	r0, #0
47f31b84:	e12fff1e 	bx	lr
47f31b88:	92140004 	andsls	r0, r4, #4
47f31b8c:	92140008 	andsls	r0, r4, #8
47f31b90:	e92d4008 	push	{r3, lr}
47f31b94:	eb0002c8 	bl	0x47f326bc
47f31b98:	eb000648 	bl	0x47f334c0
47f31b9c:	e59f3020 	ldr	r3, [pc, #32]	@ 0x47f31bc4
47f31ba0:	e3a02011 	mov	r2, #17
47f31ba4:	e3a00000 	mov	r0, #0
47f31ba8:	e5832060 	str	r2, [r3, #96]	@ 0x60
47f31bac:	e59f2014 	ldr	r2, [pc, #20]	@ 0x47f31bc8
47f31bb0:	e5d22000 	ldrb	r2, [r2]
47f31bb4:	e3520000 	cmp	r2, #0
47f31bb8:	13a02b02 	movne	r2, #2048	@ 0x800
47f31bbc:	15832070 	strne	r2, [r3, #112]	@ 0x70
47f31bc0:	e8bd8008 	pop	{r3, pc}
47f31bc4:	92140000 	andsls	r0, r4, #0
47f31bc8:	47f6219d 			@ <UNDEFINED> instruction: 0x47f6219d
47f31bcc:	e92d4010 	push	{r4, lr}
47f31bd0:	e3a04492 	mov	r4, #-1845493760	@ 0x92000000
47f31bd4:	e5943008 	ldr	r3, [r4, #8]
47f31bd8:	e1c30000 	bic	r0, r3, r0
47f31bdc:	e3800403 	orr	r0, r0, #50331648	@ 0x3000000
47f31be0:	e5840008 	str	r0, [r4, #8]
47f31be4:	e3a00064 	mov	r0, #100	@ 0x64
47f31be8:	ebffd341 	bl	0x47f268f4
47f31bec:	e3e03000 	mvn	r3, #0
47f31bf0:	e5843008 	str	r3, [r4, #8]
47f31bf4:	e8bd8010 	pop	{r4, pc}
47f31bf8:	e3a03492 	mov	r3, #-1845493760	@ 0x92000000
47f31bfc:	e3a02403 	mov	r2, #50331648	@ 0x3000000
47f31c00:	e5832008 	str	r2, [r3, #8]
47f31c04:	e12fff1e 	bx	lr
47f31c08:	e3a03492 	mov	r3, #-1845493760	@ 0x92000000
47f31c0c:	e3e02000 	mvn	r2, #0
47f31c10:	e5832008 	str	r2, [r3, #8]
47f31c14:	e12fff1e 	bx	lr
47f31c18:	e59f3004 	ldr	r3, [pc, #4]	@ 0x47f31c24
47f31c1c:	e5930000 	ldr	r0, [r3]
47f31c20:	e12fff1e 	bx	lr
47f31c24:	47f6224c 	ldrbmi	r2, [r6, r12, asr #4]!
47f31c28:	e92d4070 	push	{r4, r5, r6, lr}
47f31c2c:	e59f5048 	ldr	r5, [pc, #72]	@ 0x47f31c7c
47f31c30:	e5956000 	ldr	r6, [r5]
47f31c34:	e3560000 	cmp	r6, #0
47f31c38:	1a00000d 	bne	0x47f31c74
47f31c3c:	e3a04492 	mov	r4, #-1845493760	@ 0x92000000
47f31c40:	e3e00000 	mvn	r0, #0
47f31c44:	ebffffe0 	bl	0x47f31bcc
47f31c48:	ebffffd0 	bl	0x47f31b90
47f31c4c:	e3a0300f 	mov	r3, #15
47f31c50:	e5846018 	str	r6, [r4, #24]
47f31c54:	e3a00ffa 	mov	r0, #1000	@ 0x3e8
47f31c58:	e584301c 	str	r3, [r4, #28]
47f31c5c:	ebffd324 	bl	0x47f268f4
47f31c60:	e594300c 	ldr	r3, [r4, #12]
47f31c64:	e3833802 	orr	r3, r3, #131072	@ 0x20000
47f31c68:	e584300c 	str	r3, [r4, #12]
47f31c6c:	e3a03001 	mov	r3, #1
47f31c70:	e5853000 	str	r3, [r5]
47f31c74:	e3a00000 	mov	r0, #0
47f31c78:	e8bd8070 	pop	{r4, r5, r6, pc}
47f31c7c:	47f6224c 	ldrbmi	r2, [r6, r12, asr #4]!
47f31c80:	e59f3098 	ldr	r3, [pc, #152]	@ 0x47f31d20
47f31c84:	e3072f9f 	movw	r2, #32671	@ 0x7f9f
47f31c88:	e92d4010 	push	{r4, lr}
47f31c8c:	e3a00ffa 	mov	r0, #1000	@ 0x3e8
47f31c90:	e5832004 	str	r2, [r3, #4]
47f31c94:	e59f4088 	ldr	r4, [pc, #136]	@ 0x47f31d24
47f31c98:	e59f3088 	ldr	r3, [pc, #136]	@ 0x47f31d28
47f31c9c:	e5843000 	str	r3, [r4]
47f31ca0:	ebffd313 	bl	0x47f268f4
47f31ca4:	e5941014 	ldr	r1, [r4, #20]
47f31ca8:	e59f407c 	ldr	r4, [pc, #124]	@ 0x47f31d2c
47f31cac:	e3110020 	tst	r1, #32
47f31cb0:	1a00000b 	bne	0x47f31ce4
47f31cb4:	e351000a 	cmp	r1, #10
47f31cb8:	1a000002 	bne	0x47f31cc8
47f31cbc:	e59f006c 	ldr	r0, [pc, #108]	@ 0x47f31d30
47f31cc0:	ebff6224 	bl	0x47f0a558
47f31cc4:	ea000008 	b	0x47f31cec
47f31cc8:	e59f0064 	ldr	r0, [pc, #100]	@ 0x47f31d34
47f31ccc:	ebff6221 	bl	0x47f0a558
47f31cd0:	e3a03004 	mov	r3, #4
47f31cd4:	e59f005c 	ldr	r0, [pc, #92]	@ 0x47f31d38
47f31cd8:	e5843004 	str	r3, [r4, #4]
47f31cdc:	e59f1058 	ldr	r1, [pc, #88]	@ 0x47f31d3c
47f31ce0:	ea000005 	b	0x47f31cfc
47f31ce4:	e59f0054 	ldr	r0, [pc, #84]	@ 0x47f31d40
47f31ce8:	ebff621a 	bl	0x47f0a558
47f31cec:	e59f0044 	ldr	r0, [pc, #68]	@ 0x47f31d38
47f31cf0:	e3a03008 	mov	r3, #8
47f31cf4:	e59f1048 	ldr	r1, [pc, #72]	@ 0x47f31d44
47f31cf8:	e5843004 	str	r3, [r4, #4]
47f31cfc:	ebff5df6 	bl	0x47f094dc
47f31d00:	e59f3018 	ldr	r3, [pc, #24]	@ 0x47f31d20
47f31d04:	e3072fff 	movw	r2, #32767	@ 0x7fff
47f31d08:	e3a00000 	mov	r0, #0
47f31d0c:	e5832004 	str	r2, [r3, #4]
47f31d10:	e2833901 	add	r3, r3, #16384	@ 0x4000
47f31d14:	e59f202c 	ldr	r2, [pc, #44]	@ 0x47f31d48
47f31d18:	e5832000 	str	r2, [r3]
47f31d1c:	e8bd8010 	pop	{r4, pc}
47f31d20:	920c0000 	andls	r0, r12, #0
47f31d24:	920c4000 	andls	r4, r12, #0
47f31d28:	07d0052f 	ldrbeq	r0, [r0, pc, lsr #10]
47f31d2c:	47f6224c 	ldrbmi	r2, [r6, r12, asr #4]!
47f31d30:	47f44429 	ldrbmi	r4, [r4, r9, lsr #8]!
47f31d34:	47f44451 	ubfxmi	r4, r1, #8, #21
47f31d38:	47f44444 	ldrbmi	r4, [r4, r4, asr #8]!
47f31d3c:	47f4447c 			@ <UNDEFINED> instruction: 0x47f4447c
47f31d40:	47f44481 	ldrbmi	r4, [r4, r1, lsl #9]!
47f31d44:	47f4444c 	ldrbmi	r4, [r4, r12, asr #8]!
47f31d48:	07d0000c 	ldrbeq	r0, [r0, r12]
47f31d4c:	e59f3080 	ldr	r3, [pc, #128]	@ 0x47f31dd4
47f31d50:	e3a01010 	mov	r1, #16
47f31d54:	e59f207c 	ldr	r2, [pc, #124]	@ 0x47f31dd8
47f31d58:	e5832000 	str	r2, [r3]
47f31d5c:	e3a02000 	mov	r2, #0
47f31d60:	e5832004 	str	r2, [r3, #4]
47f31d64:	e5832008 	str	r2, [r3, #8]
47f31d68:	e583100c 	str	r1, [r3, #12]
47f31d6c:	e59f1068 	ldr	r1, [pc, #104]	@ 0x47f31ddc
47f31d70:	e5832010 	str	r2, [r3, #16]
47f31d74:	e5831014 	str	r1, [r3, #20]
47f31d78:	e3a01722 	mov	r1, #8912896	@ 0x880000
47f31d7c:	e5832018 	str	r2, [r3, #24]
47f31d80:	e5832140 	str	r2, [r3, #320]	@ 0x140
47f31d84:	e5832144 	str	r2, [r3, #324]	@ 0x144
47f31d88:	e5831148 	str	r1, [r3, #328]	@ 0x148
47f31d8c:	e59f104c 	ldr	r1, [pc, #76]	@ 0x47f31de0
47f31d90:	e583114c 	str	r1, [r3, #332]	@ 0x14c
47f31d94:	e3041de8 	movw	r1, #19944	@ 0x4de8
47f31d98:	e5832150 	str	r2, [r3, #336]	@ 0x150
47f31d9c:	e5832154 	str	r2, [r3, #340]	@ 0x154
47f31da0:	e5831280 	str	r1, [r3, #640]	@ 0x280
47f31da4:	e3a01841 	mov	r1, #4259840	@ 0x410000
47f31da8:	e5832284 	str	r2, [r3, #644]	@ 0x284
47f31dac:	e5832288 	str	r2, [r3, #648]	@ 0x288
47f31db0:	e583228c 	str	r2, [r3, #652]	@ 0x28c
47f31db4:	e5832290 	str	r2, [r3, #656]	@ 0x290
47f31db8:	e58312c0 	str	r1, [r3, #704]	@ 0x2c0
47f31dbc:	e59f1020 	ldr	r1, [pc, #32]	@ 0x47f31de4
47f31dc0:	e58322c4 	str	r2, [r3, #708]	@ 0x2c4
47f31dc4:	e58312c8 	str	r1, [r3, #712]	@ 0x2c8
47f31dc8:	e58322cc 	str	r2, [r3, #716]	@ 0x2cc
47f31dcc:	e58322d0 	str	r2, [r3, #720]	@ 0x2d0
47f31dd0:	e12fff1e 	bx	lr
47f31dd4:	9fe00000 	svcls	0x00e00000
47f31dd8:	140040c0 	strne	r4, [r0], #-192	@ 0xffffff40
47f31ddc:	02028000 	andeq	r8, r2, #0
47f31de0:	0002ad80 	andeq	r10, r2, r0, lsl #27
47f31de4:	7eccd000 	cdpvc	0, 12, cr13, cr12, cr0, {0}
47f31de8:	e92d40f8 	push	{r3, r4, r5, r6, r7, lr}
47f31dec:	e59f533c 	ldr	r5, [pc, #828]	@ 0x47f32130
47f31df0:	e5953000 	ldr	r3, [r5]
47f31df4:	e3530000 	cmp	r3, #0
47f31df8:	1a0000ca 	bne	0x47f32128
47f31dfc:	e59f2330 	ldr	r2, [pc, #816]	@ 0x47f32134
47f31e00:	e3a04325 	mov	r4, #-1811939328	@ 0x94000000
47f31e04:	e5923030 	ldr	r3, [r2, #48]	@ 0x30
47f31e08:	e3c33078 	bic	r3, r3, #120	@ 0x78
47f31e0c:	e3833080 	orr	r3, r3, #128	@ 0x80
47f31e10:	e5823030 	str	r3, [r2, #48]	@ 0x30
47f31e14:	e5943008 	ldr	r3, [r4, #8]
47f31e18:	e3c32010 	bic	r2, r3, #16
47f31e1c:	e3833020 	orr	r3, r3, #32
47f31e20:	e5842008 	str	r2, [r4, #8]
47f31e24:	e5843008 	str	r3, [r4, #8]
47f31e28:	ebffffc7 	bl	0x47f31d4c
47f31e2c:	e3a00064 	mov	r0, #100	@ 0x64
47f31e30:	ebffd2bb 	bl	0x47f26924
47f31e34:	e59f02fc 	ldr	r0, [pc, #764]	@ 0x47f32138
47f31e38:	ebff61c6 	bl	0x47f0a558
47f31e3c:	e59f22f8 	ldr	r2, [pc, #760]	@ 0x47f3213c
47f31e40:	e5943008 	ldr	r3, [r4, #8]
47f31e44:	e3833010 	orr	r3, r3, #16
47f31e48:	e5843008 	str	r3, [r4, #8]
47f31e4c:	e594300c 	ldr	r3, [r4, #12]
47f31e50:	e5920000 	ldr	r0, [r2]
47f31e54:	e59f12e4 	ldr	r1, [pc, #740]	@ 0x47f32140
47f31e58:	e3c33e1e 	bic	r3, r3, #480	@ 0x1e0
47f31e5c:	e38330a0 	orr	r3, r3, #160	@ 0xa0
47f31e60:	e584300c 	str	r3, [r4, #12]
47f31e64:	e1500001 	cmp	r0, r1
47f31e68:	0594300c 	ldreq	r3, [r4, #12]
47f31e6c:	03c33606 	biceq	r3, r3, #6291456	@ 0x600000
47f31e70:	03833602 	orreq	r3, r3, #2097152	@ 0x200000
47f31e74:	0584300c 	streq	r3, [r4, #12]
47f31e78:	e5922000 	ldr	r2, [r2]
47f31e7c:	e59f32c0 	ldr	r3, [pc, #704]	@ 0x47f32144
47f31e80:	e1520003 	cmp	r2, r3
47f31e84:	1a0000a5 	bne	0x47f32120
47f31e88:	e59f42a4 	ldr	r4, [pc, #676]	@ 0x47f32134
47f31e8c:	e59f02b4 	ldr	r0, [pc, #692]	@ 0x47f32148
47f31e90:	ebff61b0 	bl	0x47f0a558
47f31e94:	e3013148 	movw	r3, #4424	@ 0x1148
47f31e98:	e3a0000a 	mov	r0, #10
47f31e9c:	e5843014 	str	r3, [r4, #20]
47f31ea0:	e3013168 	movw	r3, #4456	@ 0x1168
47f31ea4:	e5843018 	str	r3, [r4, #24]
47f31ea8:	e3013188 	movw	r3, #4488	@ 0x1188
47f31eac:	e584301c 	str	r3, [r4, #28]
47f31eb0:	ebffd29b 	bl	0x47f26924
47f31eb4:	e59f3290 	ldr	r3, [pc, #656]	@ 0x47f3214c
47f31eb8:	e3a00010 	mov	r0, #16
47f31ebc:	e5843014 	str	r3, [r4, #20]
47f31ec0:	ebffd297 	bl	0x47f26924
47f31ec4:	e59f3284 	ldr	r3, [pc, #644]	@ 0x47f32150
47f31ec8:	e3a00010 	mov	r0, #16
47f31ecc:	e5843018 	str	r3, [r4, #24]
47f31ed0:	ebffd293 	bl	0x47f26924
47f31ed4:	e59f3278 	ldr	r3, [pc, #632]	@ 0x47f32154
47f31ed8:	e3a00010 	mov	r0, #16
47f31edc:	e584301c 	str	r3, [r4, #28]
47f31ee0:	ebffd28f 	bl	0x47f26924
47f31ee4:	e59f326c 	ldr	r3, [pc, #620]	@ 0x47f32158
47f31ee8:	e5932200 	ldr	r2, [r3, #512]	@ 0x200
47f31eec:	e5933204 	ldr	r3, [r3, #516]	@ 0x204
47f31ef0:	e5941014 	ldr	r1, [r4, #20]
47f31ef4:	e7e32c52 	ubfx	r2, r2, #24, #4
47f31ef8:	e2822001 	add	r2, r2, #1
47f31efc:	e3c11702 	bic	r1, r1, #524288	@ 0x80000
47f31f00:	e3c1100f 	bic	r1, r1, #15
47f31f04:	e3811702 	orr	r1, r1, #524288	@ 0x80000
47f31f08:	e1812002 	orr	r2, r1, r2
47f31f0c:	e5842014 	str	r2, [r4, #20]
47f31f10:	e5942018 	ldr	r2, [r4, #24]
47f31f14:	e203100f 	and	r1, r3, #15
47f31f18:	e2811001 	add	r1, r1, #1
47f31f1c:	e7e33253 	ubfx	r3, r3, #4, #4
47f31f20:	e3c22702 	bic	r2, r2, #524288	@ 0x80000
47f31f24:	e2833001 	add	r3, r3, #1
47f31f28:	e3c2200f 	bic	r2, r2, #15
47f31f2c:	e3822702 	orr	r2, r2, #524288	@ 0x80000
47f31f30:	e1822001 	orr	r2, r2, r1
47f31f34:	e5842018 	str	r2, [r4, #24]
47f31f38:	e594201c 	ldr	r2, [r4, #28]
47f31f3c:	e3c22702 	bic	r2, r2, #524288	@ 0x80000
47f31f40:	e3c2200f 	bic	r2, r2, #15
47f31f44:	e3822702 	orr	r2, r2, #524288	@ 0x80000
47f31f48:	e1823003 	orr	r3, r2, r3
47f31f4c:	e584301c 	str	r3, [r4, #28]
47f31f50:	e59f3204 	ldr	r3, [pc, #516]	@ 0x47f3215c
47f31f54:	e5936000 	ldr	r6, [r3]
47f31f58:	e1a07003 	mov	r7, r3
47f31f5c:	e5973000 	ldr	r3, [r7]
47f31f60:	e59f41f4 	ldr	r4, [pc, #500]	@ 0x47f3215c
47f31f64:	e2833003 	add	r3, r3, #3
47f31f68:	e1560003 	cmp	r6, r3
47f31f6c:	2a000061 	bcs	0x47f320f8
47f31f70:	e6ef4076 	uxtb	r4, r6
47f31f74:	e3a0201f 	mov	r2, #31
47f31f78:	e3a03c01 	mov	r3, #256	@ 0x100
47f31f7c:	e3a00000 	mov	r0, #0
47f31f80:	e1a01004 	mov	r1, r4
47f31f84:	e2866001 	add	r6, r6, #1
47f31f88:	ebffb83a 	bl	0x47f20078
47f31f8c:	e1a01004 	mov	r1, r4
47f31f90:	e3a02012 	mov	r2, #18
47f31f94:	e3043824 	movw	r3, #18468	@ 0x4824
47f31f98:	e3a00000 	mov	r0, #0
47f31f9c:	ebffb835 	bl	0x47f20078
47f31fa0:	e1a01004 	mov	r1, r4
47f31fa4:	e3a0201f 	mov	r2, #31
47f31fa8:	e3a03c02 	mov	r3, #512	@ 0x200
47f31fac:	e3a00000 	mov	r0, #0
47f31fb0:	ebffb830 	bl	0x47f20078
47f31fb4:	e3a00000 	mov	r0, #0
47f31fb8:	e1a01004 	mov	r1, r4
47f31fbc:	e3a02018 	mov	r2, #24
47f31fc0:	e1a03000 	mov	r3, r0
47f31fc4:	ebffb82b 	bl	0x47f20078
47f31fc8:	e1a01004 	mov	r1, r4
47f31fcc:	e3a0201f 	mov	r2, #31
47f31fd0:	e3a03c06 	mov	r3, #1536	@ 0x600
47f31fd4:	e3a00000 	mov	r0, #0
47f31fd8:	ebffb826 	bl	0x47f20078
47f31fdc:	e1a01004 	mov	r1, r4
47f31fe0:	e3a02014 	mov	r2, #20
47f31fe4:	e307308f 	movw	r3, #28815	@ 0x708f
47f31fe8:	e3a00000 	mov	r0, #0
47f31fec:	ebffb821 	bl	0x47f20078
47f31ff0:	e1a01004 	mov	r1, r4
47f31ff4:	e3a02013 	mov	r2, #19
47f31ff8:	e3a03a0f 	mov	r3, #61440	@ 0xf000
47f31ffc:	e3a00000 	mov	r0, #0
47f32000:	ebffb81c 	bl	0x47f20078
47f32004:	e1a01004 	mov	r1, r4
47f32008:	e3a02015 	mov	r2, #21
47f3200c:	e3013530 	movw	r3, #5424	@ 0x1530
47f32010:	e3a00000 	mov	r0, #0
47f32014:	ebffb817 	bl	0x47f20078
47f32018:	e1a01004 	mov	r1, r4
47f3201c:	e3a0201f 	mov	r2, #31
47f32020:	e3a03b02 	mov	r3, #2048	@ 0x800
47f32024:	e3a00000 	mov	r0, #0
47f32028:	ebffb812 	bl	0x47f20078
47f3202c:	e1a01004 	mov	r1, r4
47f32030:	e3a02018 	mov	r2, #24
47f32034:	e3a030bc 	mov	r3, #188	@ 0xbc
47f32038:	e3a00000 	mov	r0, #0
47f3203c:	ebffb80d 	bl	0x47f20078
47f32040:	e3a00000 	mov	r0, #0
47f32044:	e1a01004 	mov	r1, r4
47f32048:	e3a0201f 	mov	r2, #31
47f3204c:	e1a03000 	mov	r3, r0
47f32050:	ebffb808 	bl	0x47f20078
47f32054:	e3a00000 	mov	r0, #0
47f32058:	e1a01004 	mov	r1, r4
47f3205c:	e3a0201f 	mov	r2, #31
47f32060:	e1a03000 	mov	r3, r0
47f32064:	ebffb803 	bl	0x47f20078
47f32068:	e1a01004 	mov	r1, r4
47f3206c:	e3a0200d 	mov	r2, #13
47f32070:	e3a03007 	mov	r3, #7
47f32074:	e3a00000 	mov	r0, #0
47f32078:	ebffb7fe 	bl	0x47f20078
47f3207c:	e1a01004 	mov	r1, r4
47f32080:	e3a0200e 	mov	r2, #14
47f32084:	e3a0303c 	mov	r3, #60	@ 0x3c
47f32088:	e3a00000 	mov	r0, #0
47f3208c:	ebffb7f9 	bl	0x47f20078
47f32090:	e1a01004 	mov	r1, r4
47f32094:	e3a0200d 	mov	r2, #13
47f32098:	e3043007 	movw	r3, #16391	@ 0x4007
47f3209c:	e3a00000 	mov	r0, #0
47f320a0:	ebffb7f4 	bl	0x47f20078
47f320a4:	e3a00000 	mov	r0, #0
47f320a8:	e1a01004 	mov	r1, r4
47f320ac:	e3a0200e 	mov	r2, #14
47f320b0:	e1a03000 	mov	r3, r0
47f320b4:	ebffb7ef 	bl	0x47f20078
47f320b8:	e1a01004 	mov	r1, r4
47f320bc:	e3a0201f 	mov	r2, #31
47f320c0:	e3a03c02 	mov	r3, #512	@ 0x200
47f320c4:	e3a00000 	mov	r0, #0
47f320c8:	ebffb7ea 	bl	0x47f20078
47f320cc:	e3a00000 	mov	r0, #0
47f320d0:	e1a01004 	mov	r1, r4
47f320d4:	e3a02018 	mov	r2, #24
47f320d8:	e1a03000 	mov	r3, r0
47f320dc:	ebffb7e5 	bl	0x47f20078
47f320e0:	e3a00000 	mov	r0, #0
47f320e4:	e1a01004 	mov	r1, r4
47f320e8:	e3a0201f 	mov	r2, #31
47f320ec:	e1a03000 	mov	r3, r0
47f320f0:	ebffb7e0 	bl	0x47f20078
47f320f4:	eaffff98 	b	0x47f31f5c
47f320f8:	e5d41004 	ldrb	r1, [r4, #4]
47f320fc:	e3a02010 	mov	r2, #16
47f32100:	e3083001 	movw	r3, #32769	@ 0x8001
47f32104:	e3a00000 	mov	r0, #0
47f32108:	ebffb7da 	bl	0x47f20078
47f3210c:	e3a00000 	mov	r0, #0
47f32110:	e5d41004 	ldrb	r1, [r4, #4]
47f32114:	e3a02011 	mov	r2, #17
47f32118:	e1a03000 	mov	r3, r0
47f3211c:	ebffb7d5 	bl	0x47f20078
47f32120:	e3a03001 	mov	r3, #1
47f32124:	e5853000 	str	r3, [r5]
47f32128:	e3a00000 	mov	r0, #0
47f3212c:	e8bd80f8 	pop	{r3, r4, r5, r6, r7, pc}
47f32130:	47f62254 	ubfxmi	r2, r4, #4, #23
47f32134:	94100000 	ldrls	r0, [r0], #-0
47f32138:	47f444a8 	ldrbmi	r4, [r4, r8, lsr #9]!
47f3213c:	92040000 	andls	r0, r4, #0
47f32140:	27912800 	ldrcs	r2, [r1, r0, lsl #16]
47f32144:	27912700 	ldrcs	r2, [r1, r0, lsl #14]
47f32148:	47f444ba 			@ <UNDEFINED> instruction: 0x47f444ba
47f3214c:	00081158 	andeq	r1, r8, r8, asr r1
47f32150:	00081178 	andeq	r1, r8, r8, ror r1
47f32154:	00081198 	muleq	r8, r8, r1
47f32158:	9a106000 	bls	0x4834a160
47f3215c:	47f51918 			@ <UNDEFINED> instruction: 0x47f51918
47f32160:	e59f20d8 	ldr	r2, [pc, #216]	@ 0x47f32240
47f32164:	e59f10d8 	ldr	r1, [pc, #216]	@ 0x47f32244
47f32168:	e92d4038 	push	{r3, r4, r5, lr}
47f3216c:	e3a03000 	mov	r3, #0
47f32170:	e5823000 	str	r3, [r2]
47f32174:	e5821004 	str	r1, [r2, #4]
47f32178:	e3a0103f 	mov	r1, #63	@ 0x3f
47f3217c:	e5821058 	str	r1, [r2, #88]	@ 0x58
47f32180:	e59f20c0 	ldr	r2, [pc, #192]	@ 0x47f32248
47f32184:	e59f10c0 	ldr	r1, [pc, #192]	@ 0x47f3224c
47f32188:	e1a04002 	mov	r4, r2
47f3218c:	e5821000 	str	r1, [r2]
47f32190:	e5821004 	str	r1, [r2, #4]
47f32194:	e2811902 	add	r1, r1, #32768	@ 0x8000
47f32198:	e5821008 	str	r1, [r2, #8]
47f3219c:	e582100c 	str	r1, [r2, #12]
47f321a0:	e59f10a8 	ldr	r1, [pc, #168]	@ 0x47f32250
47f321a4:	e6bf2fb3 	rev16	r2, r3
47f321a8:	e2833001 	add	r3, r3, #1
47f321ac:	e3530b02 	cmp	r3, #2048	@ 0x800
47f321b0:	e1e120b2 	strh	r2, [r1, #2]!
47f321b4:	1afffffa 	bne	0x47f321a4
47f321b8:	e59f2094 	ldr	r2, [pc, #148]	@ 0x47f32254
47f321bc:	e3a03000 	mov	r3, #0
47f321c0:	e6bf1fb3 	rev16	r1, r3
47f321c4:	e2833001 	add	r3, r3, #1
47f321c8:	e3530c02 	cmp	r3, #512	@ 0x200
47f321cc:	e1e210b2 	strh	r1, [r2, #2]!
47f321d0:	1afffffa 	bne	0x47f321c0
47f321d4:	e59f0070 	ldr	r0, [pc, #112]	@ 0x47f3224c
47f321d8:	e3a05000 	mov	r5, #0
47f321dc:	e59f1074 	ldr	r1, [pc, #116]	@ 0x47f32258
47f321e0:	e5845010 	str	r5, [r4, #16]
47f321e4:	ebff3c18 	bl	0x47f0124c
47f321e8:	e59f306c 	ldr	r3, [pc, #108]	@ 0x47f3225c
47f321ec:	e3a02441 	mov	r2, #1090519040	@ 0x41000000
47f321f0:	e1a01005 	mov	r1, r5
47f321f4:	e59f0064 	ldr	r0, [pc, #100]	@ 0x47f32260
47f321f8:	e5832020 	str	r2, [r3, #32]
47f321fc:	e2822501 	add	r2, r2, #4194304	@ 0x400000
47f32200:	e5832024 	str	r2, [r3, #36]	@ 0x24
47f32204:	e5942000 	ldr	r2, [r4]
47f32208:	e5832010 	str	r2, [r3, #16]
47f3220c:	e5942008 	ldr	r2, [r4, #8]
47f32210:	e5832014 	str	r2, [r3, #20]
47f32214:	e3a02b02 	mov	r2, #2048	@ 0x800
47f32218:	e5832028 	str	r2, [r3, #40]	@ 0x28
47f3221c:	e583202c 	str	r2, [r3, #44]	@ 0x2c
47f32220:	e2833909 	add	r3, r3, #147456	@ 0x24000
47f32224:	e3a02302 	mov	r2, #134217728	@ 0x8000000
47f32228:	e5832048 	str	r2, [r3, #72]	@ 0x48
47f3222c:	e3a02008 	mov	r2, #8
47f32230:	e5835014 	str	r5, [r3, #20]
47f32234:	ebffd10a 	bl	0x47f26664
47f32238:	e1a00005 	mov	r0, r5
47f3223c:	e8bd8038 	pop	{r3, r4, r5, pc}
47f32240:	92168000 	andsls	r8, r6, #0
47f32244:	0104c040 	tsteq	r4, r0, asr #32
47f32248:	47f62258 	ubfxmi	r2, r8, #4, #23
47f3224c:	41800000 	orrmi	r0, r0, r0
47f32250:	417ffffe 	ldrshmi	pc, [pc, #-254]	@ 0x47f3215a	@ <UNPREDICTABLE>
47f32254:	41807ffe 	strdmi	r7, [r0, lr]
47f32258:	41810000 	orrmi	r0, r1, r0
47f3225c:	92144000 	andsls	r4, r4, #0
47f32260:	47f6226c 	ldrbmi	r2, [r6, r12, ror #4]!
47f32264:	e59f3008 	ldr	r3, [pc, #8]	@ 0x47f32274
47f32268:	e3a02000 	mov	r2, #0
47f3226c:	e5832000 	str	r2, [r3]
47f32270:	e12fff1e 	bx	lr
47f32274:	92168000 	andsls	r8, r6, #0
47f32278:	e59f3008 	ldr	r3, [pc, #8]	@ 0x47f32288
47f3227c:	e3a02001 	mov	r2, #1
47f32280:	e5832000 	str	r2, [r3]
47f32284:	e12fff1e 	bx	lr
47f32288:	92168000 	andsls	r8, r6, #0
47f3228c:	e59f3060 	ldr	r3, [pc, #96]	@ 0x47f322f4
47f32290:	e5932014 	ldr	r2, [r3, #20]
47f32294:	e3520000 	cmp	r2, #0
47f32298:	03a02001 	moveq	r2, #1
47f3229c:	05832014 	streq	r2, [r3, #20]
47f322a0:	03a02004 	moveq	r2, #4
47f322a4:	1a00000c 	bne	0x47f322dc
47f322a8:	e593c014 	ldr	r12, [r3, #20]
47f322ac:	e59f1040 	ldr	r1, [pc, #64]	@ 0x47f322f4
47f322b0:	e35c0000 	cmp	r12, #0
47f322b4:	0a000002 	beq	0x47f322c4
47f322b8:	e2522001 	subs	r2, r2, #1
47f322bc:	1afffff9 	bne	0x47f322a8
47f322c0:	ea000005 	b	0x47f322dc
47f322c4:	e591000c 	ldr	r0, [r1, #12]
47f322c8:	e3500000 	cmp	r0, #0
47f322cc:	aa000002 	bge	0x47f322dc
47f322d0:	e581c014 	str	r12, [r1, #20]
47f322d4:	e6ff0070 	uxth	r0, r0
47f322d8:	e12fff1e 	bx	lr
47f322dc:	e59f2014 	ldr	r2, [pc, #20]	@ 0x47f322f8
47f322e0:	e3e0000a 	mvn	r0, #10
47f322e4:	e5923014 	ldr	r3, [r2, #20]
47f322e8:	e2833001 	add	r3, r3, #1
47f322ec:	e5823014 	str	r3, [r2, #20]
47f322f0:	e12fff1e 	bx	lr
47f322f4:	92168000 	andsls	r8, r6, #0
47f322f8:	47f62258 	ubfxmi	r2, r8, #4, #23
47f322fc:	e59f103c 	ldr	r1, [pc, #60]	@ 0x47f32340
47f32300:	e3a02004 	mov	r2, #4
47f32304:	e59130dc 	ldr	r3, [r1, #220]	@ 0xdc
47f32308:	e2133008 	ands	r3, r3, #8
47f3230c:	1a000003 	bne	0x47f32320
47f32310:	e59f2028 	ldr	r2, [pc, #40]	@ 0x47f32340
47f32314:	e5820010 	str	r0, [r2, #16]
47f32318:	e1a00003 	mov	r0, r3
47f3231c:	e12fff1e 	bx	lr
47f32320:	e2522001 	subs	r2, r2, #1
47f32324:	1afffff6 	bne	0x47f32304
47f32328:	e59f2014 	ldr	r2, [pc, #20]	@ 0x47f32344
47f3232c:	e3e0000a 	mvn	r0, #10
47f32330:	e5923018 	ldr	r3, [r2, #24]
47f32334:	e2833001 	add	r3, r3, #1
47f32338:	e5823018 	str	r3, [r2, #24]
47f3233c:	e12fff1e 	bx	lr
47f32340:	92168000 	andsls	r8, r6, #0
47f32344:	47f62258 	ubfxmi	r2, r8, #4, #23
47f32348:	e3500e11 	cmp	r0, #272	@ 0x110
47f3234c:	93a03000 	movls	r3, #0
47f32350:	83a03001 	movhi	r3, #1
47f32354:	e3510000 	cmp	r1, #0
47f32358:	03833001 	orreq	r3, r3, #1
47f3235c:	e3530000 	cmp	r3, #0
47f32360:	1a00001a 	bne	0x47f323d0
47f32364:	e92d4010 	push	{r4, lr}
47f32368:	e3a0c014 	mov	r12, #20
47f3236c:	e59fe064 	ldr	lr, [pc, #100]	@ 0x47f323d8
47f32370:	e59e4018 	ldr	r4, [lr, #24]
47f32374:	e59f305c 	ldr	r3, [pc, #92]	@ 0x47f323d8
47f32378:	e3140001 	tst	r4, #1
47f3237c:	0a00000b 	beq	0x47f323b0
47f32380:	e1800b02 	orr	r0, r0, r2, lsl #22
47f32384:	e5830014 	str	r0, [r3, #20]
47f32388:	e591200c 	ldr	r2, [r1, #12]
47f3238c:	e3a00000 	mov	r0, #0
47f32390:	e5832028 	str	r2, [r3, #40]	@ 0x28
47f32394:	e5912008 	ldr	r2, [r1, #8]
47f32398:	e5832024 	str	r2, [r3, #36]	@ 0x24
47f3239c:	e5912004 	ldr	r2, [r1, #4]
47f323a0:	e5832020 	str	r2, [r3, #32]
47f323a4:	e5912000 	ldr	r2, [r1]
47f323a8:	e583201c 	str	r2, [r3, #28]
47f323ac:	e8bd8010 	pop	{r4, pc}
47f323b0:	e25cc001 	subs	r12, r12, #1
47f323b4:	1affffed 	bne	0x47f32370
47f323b8:	e59f201c 	ldr	r2, [pc, #28]	@ 0x47f323dc
47f323bc:	e3e0000a 	mvn	r0, #10
47f323c0:	e5923008 	ldr	r3, [r2, #8]
47f323c4:	e2833001 	add	r3, r3, #1
47f323c8:	e5823008 	str	r3, [r2, #8]
47f323cc:	e8bd8010 	pop	{r4, pc}
47f323d0:	e3e00015 	mvn	r0, #21
47f323d4:	e12fff1e 	bx	lr
47f323d8:	92154000 	andsls	r4, r5, #0
47f323dc:	47f62274 			@ <UNDEFINED> instruction: 0x47f62274
47f323e0:	e3510000 	cmp	r1, #0
47f323e4:	0a000020 	beq	0x47f3246c
47f323e8:	e59fc084 	ldr	r12, [pc, #132]	@ 0x47f32474
47f323ec:	e3800302 	orr	r0, r0, #134217728	@ 0x8000000
47f323f0:	e3a02014 	mov	r2, #20
47f323f4:	e92d4010 	push	{r4, lr}
47f323f8:	e59c3018 	ldr	r3, [r12, #24]
47f323fc:	e3130001 	tst	r3, #1
47f32400:	158c0014 	strne	r0, [r12, #20]
47f32404:	13a0e014 	movne	lr, #20
47f32408:	1a000009 	bne	0x47f32434
47f3240c:	e2522001 	subs	r2, r2, #1
47f32410:	1afffff8 	bne	0x47f323f8
47f32414:	e59f205c 	ldr	r2, [pc, #92]	@ 0x47f32478
47f32418:	e3e0000a 	mvn	r0, #10
47f3241c:	e592300c 	ldr	r3, [r2, #12]
47f32420:	e2833001 	add	r3, r3, #1
47f32424:	e582300c 	str	r3, [r2, #12]
47f32428:	e8bd8010 	pop	{r4, pc}
47f3242c:	e25ee001 	subs	lr, lr, #1
47f32430:	0afffff5 	beq	0x47f3240c
47f32434:	e59c4018 	ldr	r4, [r12, #24]
47f32438:	e59f3034 	ldr	r3, [pc, #52]	@ 0x47f32474
47f3243c:	e3140001 	tst	r4, #1
47f32440:	0afffff9 	beq	0x47f3242c
47f32444:	e5932028 	ldr	r2, [r3, #40]	@ 0x28
47f32448:	e3a00000 	mov	r0, #0
47f3244c:	e581200c 	str	r2, [r1, #12]
47f32450:	e5932024 	ldr	r2, [r3, #36]	@ 0x24
47f32454:	e5812008 	str	r2, [r1, #8]
47f32458:	e5932020 	ldr	r2, [r3, #32]
47f3245c:	e5812004 	str	r2, [r1, #4]
47f32460:	e593301c 	ldr	r3, [r3, #28]
47f32464:	e5813000 	str	r3, [r1]
47f32468:	e8bd8010 	pop	{r4, pc}
47f3246c:	e3e00015 	mvn	r0, #21
47f32470:	e12fff1e 	bx	lr
47f32474:	92154000 	andsls	r4, r5, #0
47f32478:	47f62274 			@ <UNDEFINED> instruction: 0x47f62274
47f3247c:	e3530001 	cmp	r3, #1
47f32480:	93500007 	cmpls	r0, #7
47f32484:	8a00001d 	bhi	0x47f32500
47f32488:	e92d4070 	push	{r4, r5, r6, lr}
47f3248c:	e59fe074 	ldr	lr, [pc, #116]	@ 0x47f32508
47f32490:	e59f6074 	ldr	r6, [pc, #116]	@ 0x47f3250c
47f32494:	e59ec010 	ldr	r12, [lr, #16]
47f32498:	e1a0500e 	mov	r5, lr
47f3249c:	e28cc001 	add	r12, r12, #1
47f324a0:	e58ec010 	str	r12, [lr, #16]
47f324a4:	e3a0c01e 	mov	r12, #30
47f324a8:	e5964064 	ldr	r4, [r6, #100]	@ 0x64
47f324ac:	e59fe058 	ldr	lr, [pc, #88]	@ 0x47f3250c
47f324b0:	e2144001 	ands	r4, r4, #1
47f324b4:	1a000008 	bne	0x47f324dc
47f324b8:	e1a01701 	lsl	r1, r1, #14
47f324bc:	e1812202 	orr	r2, r1, r2, lsl #4
47f324c0:	e1822000 	orr	r2, r2, r0
47f324c4:	e1a00004 	mov	r0, r4
47f324c8:	e1823183 	orr	r3, r2, r3, lsl #3
47f324cc:	e58e3068 	str	r3, [lr, #104]	@ 0x68
47f324d0:	e3a03001 	mov	r3, #1
47f324d4:	e58e3064 	str	r3, [lr, #100]	@ 0x64
47f324d8:	e8bd8070 	pop	{r4, r5, r6, pc}
47f324dc:	e25cc001 	subs	r12, r12, #1
47f324e0:	1afffff0 	bne	0x47f324a8
47f324e4:	e59f0024 	ldr	r0, [pc, #36]	@ 0x47f32510
47f324e8:	ebff601a 	bl	0x47f0a558
47f324ec:	e5953004 	ldr	r3, [r5, #4]
47f324f0:	e3e0000a 	mvn	r0, #10
47f324f4:	e2833001 	add	r3, r3, #1
47f324f8:	e5853004 	str	r3, [r5, #4]
47f324fc:	e8bd8070 	pop	{r4, r5, r6, pc}
47f32500:	e3e00015 	mvn	r0, #21
47f32504:	e12fff1e 	bx	lr
47f32508:	47f62274 			@ <UNDEFINED> instruction: 0x47f62274
47f3250c:	92154000 	andsls	r4, r5, #0
47f32510:	47f444ce 	ldrbmi	r4, [r4, lr, asr #9]!
47f32514:	e92d401f 	push	{r0, r1, r2, r3, r4, lr}
47f32518:	e3a04000 	mov	r4, #0
47f3251c:	e3a03b01 	mov	r3, #1024	@ 0x400
47f32520:	e58d4008 	str	r4, [sp, #8]
47f32524:	e88d0018 	stm	sp, {r3, r4}
47f32528:	e58d400c 	str	r4, [sp, #12]
47f3252c:	e3a02000 	mov	r2, #0
47f32530:	e6ff0074 	uxth	r0, r4
47f32534:	e1a0100d 	mov	r1, sp
47f32538:	ebffff82 	bl	0x47f32348
47f3253c:	e2502000 	subs	r2, r0, #0
47f32540:	aa000004 	bge	0x47f32558
47f32544:	e59f00a8 	ldr	r0, [pc, #168]	@ 0x47f325f4
47f32548:	e1a01004 	mov	r1, r4
47f3254c:	ebff6001 	bl	0x47f0a558
47f32550:	e3e00000 	mvn	r0, #0
47f32554:	ea000024 	b	0x47f325ec
47f32558:	e2844001 	add	r4, r4, #1
47f3255c:	e3540008 	cmp	r4, #8
47f32560:	1afffff1 	bne	0x47f3252c
47f32564:	e59f308c 	ldr	r3, [pc, #140]	@ 0x47f325f8
47f32568:	e3a04000 	mov	r4, #0
47f3256c:	e58d3000 	str	r3, [sp]
47f32570:	e3a02002 	mov	r2, #2
47f32574:	e6ff0074 	uxth	r0, r4
47f32578:	e1a0100d 	mov	r1, sp
47f3257c:	ebffff71 	bl	0x47f32348
47f32580:	e2502000 	subs	r2, r0, #0
47f32584:	aa000002 	bge	0x47f32594
47f32588:	e59f006c 	ldr	r0, [pc, #108]	@ 0x47f325fc
47f3258c:	e1a01004 	mov	r1, r4
47f32590:	ebff5ff0 	bl	0x47f0a558
47f32594:	e2844001 	add	r4, r4, #1
47f32598:	e3540008 	cmp	r4, #8
47f3259c:	1afffff3 	bne	0x47f32570
47f325a0:	e3a04000 	mov	r4, #0
47f325a4:	e3a03b03 	mov	r3, #3072	@ 0xc00
47f325a8:	e58d3000 	str	r3, [sp]
47f325ac:	e3a02004 	mov	r2, #4
47f325b0:	e6ff0074 	uxth	r0, r4
47f325b4:	e1a0100d 	mov	r1, sp
47f325b8:	ebffff62 	bl	0x47f32348
47f325bc:	e2502000 	subs	r2, r0, #0
47f325c0:	aa000002 	bge	0x47f325d0
47f325c4:	e59f0034 	ldr	r0, [pc, #52]	@ 0x47f32600
47f325c8:	e1a01004 	mov	r1, r4
47f325cc:	ebff5fe1 	bl	0x47f0a558
47f325d0:	e2844001 	add	r4, r4, #1
47f325d4:	e3540008 	cmp	r4, #8
47f325d8:	1afffff3 	bne	0x47f325ac
47f325dc:	e59f3020 	ldr	r3, [pc, #32]	@ 0x47f32604
47f325e0:	e3a00000 	mov	r0, #0
47f325e4:	e3a02001 	mov	r2, #1
47f325e8:	e583206c 	str	r2, [r3, #108]	@ 0x6c
47f325ec:	e28dd010 	add	sp, sp, #16
47f325f0:	e8bd8010 	pop	{r4, pc}
47f325f4:	47f444e5 	ldrbmi	r4, [r4, r5, ror #9]!
47f325f8:	00200080 	eoreq	r0, r0, r0, lsl #1
47f325fc:	47f44507 	ldrbmi	r4, [r4, r7, lsl #10]!
47f32600:	47f44529 	ldrbmi	r4, [r4, r9, lsr #10]!
47f32604:	92154000 	andsls	r4, r5, #0
47f32608:	e59f2014 	ldr	r2, [pc, #20]	@ 0x47f32624
47f3260c:	e3500000 	cmp	r0, #0
47f32610:	e5923000 	ldr	r3, [r2]
47f32614:	e3c3380f 	bic	r3, r3, #983040	@ 0xf0000
47f32618:	1383380f 	orrne	r3, r3, #983040	@ 0xf0000
47f3261c:	e5823000 	str	r3, [r2]
47f32620:	e12fff1e 	bx	lr
47f32624:	92164000 	andsls	r4, r6, #0
47f32628:	e92d4038 	push	{r3, r4, r5, lr}
47f3262c:	e1a05000 	mov	r5, r0
47f32630:	e59f303c 	ldr	r3, [pc, #60]	@ 0x47f32674
47f32634:	e59f203c 	ldr	r2, [pc, #60]	@ 0x47f32678
47f32638:	e5931214 	ldr	r1, [r3, #532]	@ 0x214
47f3263c:	e1a04003 	mov	r4, r3
47f32640:	e2011003 	and	r1, r1, #3
47f32644:	e5821000 	str	r1, [r2]
47f32648:	e3510000 	cmp	r1, #0
47f3264c:	0a000001 	beq	0x47f32658
47f32650:	e59f0024 	ldr	r0, [pc, #36]	@ 0x47f3267c
47f32654:	ebff5fbf 	bl	0x47f0a558
47f32658:	e1a00005 	mov	r0, r5
47f3265c:	e2851020 	add	r1, r5, #32
47f32660:	ebff3af9 	bl	0x47f0124c
47f32664:	e3a03001 	mov	r3, #1
47f32668:	e3a00000 	mov	r0, #0
47f3266c:	e5843064 	str	r3, [r4, #100]	@ 0x64
47f32670:	e8bd8038 	pop	{r3, r4, r5, pc}
47f32674:	92164000 	andsls	r4, r6, #0
47f32678:	47f62288 	ldrbmi	r2, [r6, r8, lsl #5]!
47f3267c:	47f4454b 	ldrbmi	r4, [r4, r11, asr #10]!
47f32680:	e92d4008 	push	{r3, lr}
47f32684:	e3a00001 	mov	r0, #1
47f32688:	ebffffde 	bl	0x47f32608
47f3268c:	e59f301c 	ldr	r3, [pc, #28]	@ 0x47f326b0
47f32690:	e59f201c 	ldr	r2, [pc, #28]	@ 0x47f326b4
47f32694:	e3a00000 	mov	r0, #0
47f32698:	e5832050 	str	r2, [r3, #80]	@ 0x50
47f3269c:	e2822902 	add	r2, r2, #32768	@ 0x8000
47f326a0:	e5832060 	str	r2, [r3, #96]	@ 0x60
47f326a4:	e59f200c 	ldr	r2, [pc, #12]	@ 0x47f326b8
47f326a8:	e583203c 	str	r2, [r3, #60]	@ 0x3c
47f326ac:	e8bd8008 	pop	{r3, pc}
47f326b0:	92164000 	andsls	r4, r6, #0
47f326b4:	41c10000 	bicmi	r0, r1, r0
47f326b8:	00200020 	eoreq	r0, r0, r0, lsr #32
47f326bc:	e92d4038 	push	{r3, r4, r5, lr}
47f326c0:	e3a00ffa 	mov	r0, #1000	@ 0x3e8
47f326c4:	e59f304c 	ldr	r3, [pc, #76]	@ 0x47f32718
47f326c8:	e59f504c 	ldr	r5, [pc, #76]	@ 0x47f3271c
47f326cc:	e5853048 	str	r3, [r5, #72]	@ 0x48
47f326d0:	ebffd087 	bl	0x47f268f4
47f326d4:	ebffff8e 	bl	0x47f32514
47f326d8:	ebffffe8 	bl	0x47f32680
47f326dc:	eb000011 	bl	0x47f32728
47f326e0:	ebfffe9e 	bl	0x47f32160
47f326e4:	e2504000 	subs	r4, r0, #0
47f326e8:	aa000004 	bge	0x47f32700
47f326ec:	e1a01004 	mov	r1, r4
47f326f0:	e59f0028 	ldr	r0, [pc, #40]	@ 0x47f32720
47f326f4:	ebff5f97 	bl	0x47f0a558
47f326f8:	e1a00004 	mov	r0, r4
47f326fc:	e8bd8038 	pop	{r3, r4, r5, pc}
47f32700:	ebfffedc 	bl	0x47f32278
47f32704:	e59f3018 	ldr	r3, [pc, #24]	@ 0x47f32724
47f32708:	e585301c 	str	r3, [r5, #28]
47f3270c:	eb0001a1 	bl	0x47f32d98
47f32710:	e3a00000 	mov	r0, #0
47f32714:	e8bd8038 	pop	{r3, r4, r5, pc}
47f32718:	000fffff 	strdeq	pc, [pc], -pc	@ <UNPREDICTABLE>
47f3271c:	92144000 	andsls	r4, r4, #0
47f32720:	47f4455c 	ubfxmi	r4, r12, #10, #21
47f32724:	41a00000 	movmi	r0, r0
47f32728:	e59f3024 	ldr	r3, [pc, #36]	@ 0x47f32754
47f3272c:	e3a00000 	mov	r0, #0
47f32730:	e303209a 	movw	r2, #12442	@ 0x309a
47f32734:	e5832080 	str	r2, [r3, #128]	@ 0x80
47f32738:	e3a02001 	mov	r2, #1
47f3273c:	e5830088 	str	r0, [r3, #136]	@ 0x88
47f32740:	e5832014 	str	r2, [r3, #20]
47f32744:	e3a02705 	mov	r2, #1310720	@ 0x140000
47f32748:	e583202c 	str	r2, [r3, #44]	@ 0x2c
47f3274c:	e583001c 	str	r0, [r3, #28]
47f32750:	e12fff1e 	bx	lr
47f32754:	9214c000 	andsls	r12, r4, #0
47f32758:	e3510040 	cmp	r1, #64	@ 0x40
47f3275c:	e92d4070 	push	{r4, r5, r6, lr}
47f32760:	e1a06000 	mov	r6, r0
47f32764:	31a05001 	movcc	r5, r1
47f32768:	23a05040 	movcs	r5, #64	@ 0x40
47f3276c:	e3a04000 	mov	r4, #0
47f32770:	e1540005 	cmp	r4, r5
47f32774:	0a000009 	beq	0x47f327a0
47f32778:	e59f002c 	ldr	r0, [pc, #44]	@ 0x47f327ac
47f3277c:	e7d61004 	ldrb	r1, [r6, r4]
47f32780:	ebff5f74 	bl	0x47f0a558
47f32784:	e204300f 	and	r3, r4, #15
47f32788:	e353000f 	cmp	r3, #15
47f3278c:	1a000001 	bne	0x47f32798
47f32790:	e59f0018 	ldr	r0, [pc, #24]	@ 0x47f327b0
47f32794:	ebff5f6f 	bl	0x47f0a558
47f32798:	e2844001 	add	r4, r4, #1
47f3279c:	eafffff3 	b	0x47f32770
47f327a0:	e59f0008 	ldr	r0, [pc, #8]	@ 0x47f327b0
47f327a4:	e8bd4070 	pop	{r4, r5, r6, lr}
47f327a8:	eaff5f6a 	b	0x47f0a558
47f327ac:	47f42f84 	ldrbmi	r2, [r4, r4, lsl #31]!
47f327b0:	47f3ad6e 	ldrbmi	r10, [r3, lr, ror #26]!
47f327b4:	e92d4010 	push	{r4, lr}
47f327b8:	ebfffd1a 	bl	0x47f31c28
47f327bc:	e3a04000 	mov	r4, #0
47f327c0:	e6ef0074 	uxtb	r0, r4
47f327c4:	e2844001 	add	r4, r4, #1
47f327c8:	eb00026f 	bl	0x47f3318c
47f327cc:	e3540005 	cmp	r4, #5
47f327d0:	1afffffa 	bne	0x47f327c0
47f327d4:	e3a00000 	mov	r0, #0
47f327d8:	e8bd8010 	pop	{r4, pc}
47f327dc:	e92d4010 	push	{r4, lr}
47f327e0:	e3a00064 	mov	r0, #100	@ 0x64
47f327e4:	ebffd042 	bl	0x47f268f4
47f327e8:	e3a04000 	mov	r4, #0
47f327ec:	e6ef0074 	uxtb	r0, r4
47f327f0:	e2844001 	add	r4, r4, #1
47f327f4:	eb00030f 	bl	0x47f33438
47f327f8:	e3540005 	cmp	r4, #5
47f327fc:	1afffffa 	bne	0x47f327ec
47f32800:	e8bd8010 	pop	{r4, pc}
47f32804:	e59f3004 	ldr	r3, [pc, #4]	@ 0x47f32810
47f32808:	e5830000 	str	r0, [r3]
47f3280c:	e12fff1e 	bx	lr
47f32810:	47f6228c 	ldrbmi	r2, [r6, r12, lsl #5]!
47f32814:	e590300c 	ldr	r3, [r0, #12]
47f32818:	e92d4013 	push	{r0, r1, r4, lr}
47f3281c:	e1a04000 	mov	r4, r0
47f32820:	e58d3000 	str	r3, [sp]
47f32824:	e5903010 	ldr	r3, [r0, #16]
47f32828:	e59f0038 	ldr	r0, [pc, #56]	@ 0x47f32868
47f3282c:	e58d3004 	str	r3, [sp, #4]
47f32830:	e894000e 	ldm	r4, {r1, r2, r3}
47f32834:	ebff5f47 	bl	0x47f0a558
47f32838:	e59f002c 	ldr	r0, [pc, #44]	@ 0x47f3286c
47f3283c:	e994000c 	ldmib	r4, {r2, r3}
47f32840:	e1d410b8 	ldrh	r1, [r4, #8]
47f32844:	e5900004 	ldr	r0, [r0, #4]
47f32848:	e7eb2552 	ubfx	r2, r2, #10, #12
47f3284c:	e7ee1051 	ubfx	r1, r1, #0, #15
47f32850:	e7ed37d3 	ubfx	r3, r3, #15, #14
47f32854:	e58d0000 	str	r0, [sp]
47f32858:	e59f0010 	ldr	r0, [pc, #16]	@ 0x47f32870
47f3285c:	ebff5f3d 	bl	0x47f0a558
47f32860:	e28dd008 	add	sp, sp, #8
47f32864:	e8bd8010 	pop	{r4, pc}
47f32868:	47f44577 			@ <UNDEFINED> instruction: 0x47f44577
47f3286c:	47f6228c 	ldrbmi	r2, [r6, r12, lsl #5]!
47f32870:	47f4459c 			@ <UNDEFINED> instruction: 0x47f4459c
47f32874:	e92d4ef0 	push	{r4, r5, r6, r7, r9, r10, r11, lr}
47f32878:	e24dd018 	sub	sp, sp, #24
47f3287c:	e59fa204 	ldr	r10, [pc, #516]	@ 0x47f32a88
47f32880:	e3a09007 	mov	r9, #7
47f32884:	e59a3000 	ldr	r3, [r10]
47f32888:	e1a02823 	lsr	r2, r3, #16
47f3288c:	e6f23073 	uxtah	r3, r2, r3
47f32890:	e58d300c 	str	r3, [sp, #12]
47f32894:	e3530000 	cmp	r3, #0
47f32898:	da000073 	ble	0x47f32a6c
47f3289c:	e59f31e8 	ldr	r3, [pc, #488]	@ 0x47f32a8c
47f328a0:	e5933008 	ldr	r3, [r3, #8]
47f328a4:	e3530000 	cmp	r3, #0
47f328a8:	da000003 	ble	0x47f328bc
47f328ac:	e59f01dc 	ldr	r0, [pc, #476]	@ 0x47f32a90
47f328b0:	e1a01009 	mov	r1, r9
47f328b4:	e59d200c 	ldr	r2, [sp, #12]
47f328b8:	ebff5f26 	bl	0x47f0a558
47f328bc:	e1a03189 	lsl	r3, r9, #3
47f328c0:	e59f51c4 	ldr	r5, [pc, #452]	@ 0x47f32a8c
47f328c4:	e58d3014 	str	r3, [sp, #20]
47f328c8:	e59f31c4 	ldr	r3, [pc, #452]	@ 0x47f32a94
47f328cc:	e59fb1c4 	ldr	r11, [pc, #452]	@ 0x47f32a98
47f328d0:	e083308a 	add	r3, r3, r10, lsl #1
47f328d4:	e083b00b 	add	r11, r3, r11
47f328d8:	e3a03000 	mov	r3, #0
47f328dc:	e58d3010 	str	r3, [sp, #16]
47f328e0:	e59d1014 	ldr	r1, [sp, #20]
47f328e4:	e59f21a8 	ldr	r2, [pc, #424]	@ 0x47f32a94
47f328e8:	e59b3000 	ldr	r3, [r11]
47f328ec:	e7914002 	ldr	r4, [r1, r2]
47f328f0:	e0844203 	add	r4, r4, r3, lsl #4
47f328f4:	e2833001 	add	r3, r3, #1
47f328f8:	e3530b01 	cmp	r3, #1024	@ 0x400
47f328fc:	e58b3000 	str	r3, [r11]
47f32900:	e1a00004 	mov	r0, r4
47f32904:	e2841010 	add	r1, r4, #16
47f32908:	23a03000 	movcs	r3, #0
47f3290c:	258b3000 	strcs	r3, [r11]
47f32910:	ebff3a68 	bl	0x47f012b8
47f32914:	e1d460b8 	ldrh	r6, [r4, #8]
47f32918:	e7ee3056 	ubfx	r3, r6, #0, #15
47f3291c:	e58d3008 	str	r3, [sp, #8]
47f32920:	e3530b02 	cmp	r3, #2048	@ 0x800
47f32924:	ba00000a 	blt	0x47f32954
47f32928:	e1a01003 	mov	r1, r3
47f3292c:	e59f0168 	ldr	r0, [pc, #360]	@ 0x47f32a9c
47f32930:	ebff5f08 	bl	0x47f0a558
47f32934:	e1a00004 	mov	r0, r4
47f32938:	ebffffb5 	bl	0x47f32814
47f3293c:	e3a02001 	mov	r2, #1
47f32940:	e6ef0079 	uxtb	r0, r9
47f32944:	e3a01000 	mov	r1, #0
47f32948:	e1a03002 	mov	r3, r2
47f3294c:	ebfffeca 	bl	0x47f3247c
47f32950:	ea000038 	b	0x47f32a38
47f32954:	e59d3008 	ldr	r3, [sp, #8]
47f32958:	e5947008 	ldr	r7, [r4, #8]
47f3295c:	e1a0c583 	lsl	r12, r3, #11
47f32960:	e7ed77d7 	ubfx	r7, r7, #15, #14
47f32964:	e28c6441 	add	r6, r12, #1090519040	@ 0x41000000
47f32968:	e2866010 	add	r6, r6, #16
47f3296c:	e0861007 	add	r1, r6, r7
47f32970:	e1a00006 	mov	r0, r6
47f32974:	ebff3a4f 	bl	0x47f012b8
47f32978:	e5953008 	ldr	r3, [r5, #8]
47f3297c:	e3530000 	cmp	r3, #0
47f32980:	da00000e 	ble	0x47f329c0
47f32984:	e1a00004 	mov	r0, r4
47f32988:	ebffffa1 	bl	0x47f32814
47f3298c:	e5943004 	ldr	r3, [r4, #4]
47f32990:	e1a01007 	mov	r1, r7
47f32994:	e59d2008 	ldr	r2, [sp, #8]
47f32998:	e7eb3553 	ubfx	r3, r3, #10, #12
47f3299c:	e58d6000 	str	r6, [sp]
47f329a0:	e59f00f8 	ldr	r0, [pc, #248]	@ 0x47f32aa0
47f329a4:	ebff5eeb 	bl	0x47f0a558
47f329a8:	e1a00006 	mov	r0, r6
47f329ac:	e1a01007 	mov	r1, r7
47f329b0:	ebffff68 	bl	0x47f32758
47f329b4:	e5953008 	ldr	r3, [r5, #8]
47f329b8:	e2433001 	sub	r3, r3, #1
47f329bc:	e5853008 	str	r3, [r5, #8]
47f329c0:	e5953004 	ldr	r3, [r5, #4]
47f329c4:	e2833001 	add	r3, r3, #1
47f329c8:	e5853004 	str	r3, [r5, #4]
47f329cc:	e5953000 	ldr	r3, [r5]
47f329d0:	e3530000 	cmp	r3, #0
47f329d4:	1a000003 	bne	0x47f329e8
47f329d8:	e1a00006 	mov	r0, r6
47f329dc:	e1a01007 	mov	r1, r7
47f329e0:	ebffece3 	bl	0x47f2dd74
47f329e4:	ea000003 	b	0x47f329f8
47f329e8:	e5953000 	ldr	r3, [r5]
47f329ec:	e1a00006 	mov	r0, r6
47f329f0:	e1a01007 	mov	r1, r7
47f329f4:	e12fff33 	blx	r3
47f329f8:	e5d40003 	ldrb	r0, [r4, #3]
47f329fc:	e3a02001 	mov	r2, #1
47f32a00:	e3a01000 	mov	r1, #0
47f32a04:	e1a03002 	mov	r3, r2
47f32a08:	e1a002a0 	lsr	r0, r0, #5
47f32a0c:	ebfffe9a 	bl	0x47f3247c
47f32a10:	e3500000 	cmp	r0, #0
47f32a14:	aa000001 	bge	0x47f32a20
47f32a18:	e59f0084 	ldr	r0, [pc, #132]	@ 0x47f32aa4
47f32a1c:	ebff5ecd 	bl	0x47f0a558
47f32a20:	e59d0008 	ldr	r0, [sp, #8]
47f32a24:	ebfffe34 	bl	0x47f322fc
47f32a28:	e3500000 	cmp	r0, #0
47f32a2c:	aa000001 	bge	0x47f32a38
47f32a30:	e59f0070 	ldr	r0, [pc, #112]	@ 0x47f32aa8
47f32a34:	ebff5ec7 	bl	0x47f0a558
47f32a38:	e59d3010 	ldr	r3, [sp, #16]
47f32a3c:	e59d200c 	ldr	r2, [sp, #12]
47f32a40:	e2833001 	add	r3, r3, #1
47f32a44:	e58d3010 	str	r3, [sp, #16]
47f32a48:	e1530002 	cmp	r3, r2
47f32a4c:	1affffa3 	bne	0x47f328e0
47f32a50:	e59a3000 	ldr	r3, [r10]
47f32a54:	e1a02823 	lsr	r2, r3, #16
47f32a58:	e6f23073 	uxtah	r3, r2, r3
47f32a5c:	e3530000 	cmp	r3, #0
47f32a60:	0a000001 	beq	0x47f32a6c
47f32a64:	e3a00001 	mov	r0, #1
47f32a68:	ebffcfa1 	bl	0x47f268f4
47f32a6c:	e2499001 	sub	r9, r9, #1
47f32a70:	e24aa004 	sub	r10, r10, #4
47f32a74:	e3790001 	cmn	r9, #1
47f32a78:	1affff81 	bne	0x47f32884
47f32a7c:	e3a00000 	mov	r0, #0
47f32a80:	e28dd018 	add	sp, sp, #24
47f32a84:	e8bd8ef0 	pop	{r4, r5, r6, r7, r9, r10, r11, pc}
47f32a88:	9216411c 	andsls	r4, r6, #28, 2
47f32a8c:	47f6228c 	ldrbmi	r2, [r6, r12, lsl #5]!
47f32a90:	47f445c1 	ldrbmi	r4, [r4, r1, asr #11]!
47f32a94:	47f62298 			@ <UNDEFINED> instruction: 0x47f62298
47f32a98:	dbd37e04 	blle	0x474122b0
47f32a9c:	47f445d2 	ubfxmi	r4, r2, #11, #21
47f32aa0:	47f445e1 	ldrbmi	r4, [r4, r1, ror #11]!
47f32aa4:	47f44608 	ldrbmi	r4, [r4, r8, lsl #12]!
47f32aa8:	47f44620 	ldrbmi	r4, [r4, r0, lsr #12]!
47f32aac:	e5903008 	ldr	r3, [r0, #8]
47f32ab0:	e92d4037 	push	{r0, r1, r2, r4, r5, lr}
47f32ab4:	e1a04000 	mov	r4, r0
47f32ab8:	e59f5064 	ldr	r5, [pc, #100]	@ 0x47f32b24
47f32abc:	e1a01004 	mov	r1, r4
47f32ac0:	e58d3000 	str	r3, [sp]
47f32ac4:	e590300c 	ldr	r3, [r0, #12]
47f32ac8:	e1a00005 	mov	r0, r5
47f32acc:	e58d3004 	str	r3, [sp, #4]
47f32ad0:	e894000c 	ldm	r4, {r2, r3}
47f32ad4:	ebff5e9f 	bl	0x47f0a558
47f32ad8:	e5943018 	ldr	r3, [r4, #24]
47f32adc:	e2841010 	add	r1, r4, #16
47f32ae0:	e5942010 	ldr	r2, [r4, #16]
47f32ae4:	e1a00005 	mov	r0, r5
47f32ae8:	e58d3000 	str	r3, [sp]
47f32aec:	e594301c 	ldr	r3, [r4, #28]
47f32af0:	e58d3004 	str	r3, [sp, #4]
47f32af4:	e5943014 	ldr	r3, [r4, #20]
47f32af8:	ebff5e96 	bl	0x47f0a558
47f32afc:	e5941008 	ldr	r1, [r4, #8]
47f32b00:	e1d420b8 	ldrh	r2, [r4, #8]
47f32b04:	e594300c 	ldr	r3, [r4, #12]
47f32b08:	e7ee1751 	ubfx	r1, r1, #14, #15
47f32b0c:	e59f0014 	ldr	r0, [pc, #20]	@ 0x47f32b28
47f32b10:	e7eb2152 	ubfx	r2, r2, #2, #12
47f32b14:	e7ed36d3 	ubfx	r3, r3, #13, #14
47f32b18:	e28dd00c 	add	sp, sp, #12
47f32b1c:	e8bd4030 	pop	{r4, r5, lr}
47f32b20:	eaff5e8c 	b	0x47f0a558
47f32b24:	47f44632 			@ <UNDEFINED> instruction: 0x47f44632
47f32b28:	47f44656 	ubfxmi	r4, r6, #12, #21
47f32b2c:	e92d42f0 	push	{r4, r5, r6, r7, r9, lr}
47f32b30:	e1a09000 	mov	r9, r0
47f32b34:	e1a06001 	mov	r6, r1
47f32b38:	e1a04002 	mov	r4, r2
47f32b3c:	ebfffdd2 	bl	0x47f3228c
47f32b40:	e2507000 	subs	r7, r0, #0
47f32b44:	aa000002 	bge	0x47f32b54
47f32b48:	e59f00f8 	ldr	r0, [pc, #248]	@ 0x47f32c48
47f32b4c:	ebff5e81 	bl	0x47f0a558
47f32b50:	ea000004 	b	0x47f32b68
47f32b54:	e3570b02 	cmp	r7, #2048	@ 0x800
47f32b58:	ba000004 	blt	0x47f32b70
47f32b5c:	e59f00e8 	ldr	r0, [pc, #232]	@ 0x47f32c4c
47f32b60:	e1a01007 	mov	r1, r7
47f32b64:	ebff5e7b 	bl	0x47f0a558
47f32b68:	e3e00000 	mvn	r0, #0
47f32b6c:	e8bd82f0 	pop	{r4, r5, r6, r7, r9, pc}
47f32b70:	e1a05587 	lsl	r5, r7, #11
47f32b74:	e1a01009 	mov	r1, r9
47f32b78:	e2855441 	add	r5, r5, #1090519040	@ 0x41000000
47f32b7c:	e1a02006 	mov	r2, r6
47f32b80:	e2855010 	add	r5, r5, #16
47f32b84:	e1a00005 	mov	r0, r5
47f32b88:	ebffced5 	bl	0x47f266e4
47f32b8c:	e5943008 	ldr	r3, [r4, #8]
47f32b90:	e7ed2056 	ubfx	r2, r6, #0, #14
47f32b94:	e1d411b0 	ldrh	r1, [r4, #16]
47f32b98:	e7dc3717 	bfi	r3, r7, #14, #15
47f32b9c:	e5843008 	str	r3, [r4, #8]
47f32ba0:	e594300c 	ldr	r3, [r4, #12]
47f32ba4:	e3560000 	cmp	r6, #0
47f32ba8:	e7cd1012 	bfi	r1, r2, #0, #14
47f32bac:	e1c411b0 	strh	r1, [r4, #16]
47f32bb0:	e7da3692 	bfi	r3, r2, #13, #14
47f32bb4:	e3a02010 	mov	r2, #16
47f32bb8:	e584300c 	str	r3, [r4, #12]
47f32bbc:	e7cc3392 	bfi	r3, r2, #7, #6
47f32bc0:	e1c430bc 	strh	r3, [r4, #12]
47f32bc4:	1a000001 	bne	0x47f32bd0
47f32bc8:	e59f0080 	ldr	r0, [pc, #128]	@ 0x47f32c50
47f32bcc:	ebff5e61 	bl	0x47f0a558
47f32bd0:	e59f907c 	ldr	r9, [pc, #124]	@ 0x47f32c54
47f32bd4:	e5993008 	ldr	r3, [r9, #8]
47f32bd8:	e3530000 	cmp	r3, #0
47f32bdc:	da00000c 	ble	0x47f32c14
47f32be0:	e1a03005 	mov	r3, r5
47f32be4:	e1a01006 	mov	r1, r6
47f32be8:	e1a02007 	mov	r2, r7
47f32bec:	e59f0064 	ldr	r0, [pc, #100]	@ 0x47f32c58
47f32bf0:	ebff5e58 	bl	0x47f0a558
47f32bf4:	e1a00004 	mov	r0, r4
47f32bf8:	ebffffab 	bl	0x47f32aac
47f32bfc:	e1a00005 	mov	r0, r5
47f32c00:	e1a01006 	mov	r1, r6
47f32c04:	ebfffed3 	bl	0x47f32758
47f32c08:	e5993008 	ldr	r3, [r9, #8]
47f32c0c:	e2433001 	sub	r3, r3, #1
47f32c10:	e5893008 	str	r3, [r9, #8]
47f32c14:	e1a00005 	mov	r0, r5
47f32c18:	e0851006 	add	r1, r5, r6
47f32c1c:	ebff398a 	bl	0x47f0124c
47f32c20:	e1a00004 	mov	r0, r4
47f32c24:	ebfffe7f 	bl	0x47f32628
47f32c28:	e3500000 	cmp	r0, #0
47f32c2c:	aa000003 	bge	0x47f32c40
47f32c30:	e59f0024 	ldr	r0, [pc, #36]	@ 0x47f32c5c
47f32c34:	ebff5e47 	bl	0x47f0a558
47f32c38:	e3e00001 	mvn	r0, #1
47f32c3c:	e8bd82f0 	pop	{r4, r5, r6, r7, r9, pc}
47f32c40:	e3a00000 	mov	r0, #0
47f32c44:	e8bd82f0 	pop	{r4, r5, r6, r7, r9, pc}
47f32c48:	47f4466c 	ldrbmi	r4, [r4, r12, ror #12]!
47f32c4c:	47f4467d 			@ <UNDEFINED> instruction: 0x47f4467d
47f32c50:	47f4468c 	ldrbmi	r4, [r4, r12, lsl #13]!
47f32c54:	47f6228c 	ldrbmi	r2, [r6, r12, lsl #5]!
47f32c58:	47f44699 			@ <UNDEFINED> instruction: 0x47f44699
47f32c5c:	47f446b6 			@ <UNDEFINED> instruction: 0x47f446b6
47f32c60:	e59f30d8 	ldr	r3, [pc, #216]	@ 0x47f32d40
47f32c64:	e92d4010 	push	{r4, lr}
47f32c68:	e593c04c 	ldr	r12, [r3, #76]	@ 0x4c
47f32c6c:	e35c0009 	cmp	r12, #9
47f32c70:	859f00cc 	ldrhi	r0, [pc, #204]	@ 0x47f32d44
47f32c74:	8590e068 	ldrhi	lr, [r0, #104]	@ 0x68
47f32c78:	86ffe07e 	uxthhi	lr, lr
47f32c7c:	806ec00c 	rsbhi	r12, lr, r12
47f32c80:	8583c04c 	strhi	r12, [r3, #76]	@ 0x4c
47f32c84:	e593304c 	ldr	r3, [r3, #76]	@ 0x4c
47f32c88:	e59fc0b0 	ldr	r12, [pc, #176]	@ 0x47f32d40
47f32c8c:	e3530c02 	cmp	r3, #512	@ 0x200
47f32c90:	3a00000c 	bcc	0x47f32cc8
47f32c94:	e59f20a8 	ldr	r2, [pc, #168]	@ 0x47f32d44
47f32c98:	e5922068 	ldr	r2, [r2, #104]	@ 0x68
47f32c9c:	e3520402 	cmp	r2, #33554432	@ 0x2000000
47f32ca0:	e6ff1072 	uxth	r1, r2
47f32ca4:	e0613003 	rsb	r3, r1, r3
47f32ca8:	e58c304c 	str	r3, [r12, #76]	@ 0x4c
47f32cac:	259c3050 	ldrcs	r3, [r12, #80]	@ 0x50
47f32cb0:	359c3054 	ldrcc	r3, [r12, #84]	@ 0x54
47f32cb4:	22833001 	addcs	r3, r3, #1
47f32cb8:	32833001 	addcc	r3, r3, #1
47f32cbc:	258c3050 	strcs	r3, [r12, #80]	@ 0x50
47f32cc0:	358c3054 	strcc	r3, [r12, #84]	@ 0x54
47f32cc4:	ea000009 	b	0x47f32cf0
47f32cc8:	e59ce058 	ldr	lr, [r12, #88]	@ 0x58
47f32ccc:	e59c005c 	ldr	r0, [r12, #92]	@ 0x5c
47f32cd0:	e28e4001 	add	r4, lr, #1
47f32cd4:	e58c4058 	str	r4, [r12, #88]	@ 0x58
47f32cd8:	e3540c02 	cmp	r4, #512	@ 0x200
47f32cdc:	e080328e 	add	r3, r0, lr, lsl #5
47f32ce0:	23a04000 	movcs	r4, #0
47f32ce4:	258c4058 	strcs	r4, [r12, #88]	@ 0x58
47f32ce8:	e3530000 	cmp	r3, #0
47f32cec:	1a000003 	bne	0x47f32d00
47f32cf0:	e59f0050 	ldr	r0, [pc, #80]	@ 0x47f32d48
47f32cf4:	ebff5e17 	bl	0x47f0a558
47f32cf8:	e3e00000 	mvn	r0, #0
47f32cfc:	e8bd8010 	pop	{r4, pc}
47f32d00:	e3a04000 	mov	r4, #0
47f32d04:	e3a0c222 	mov	r12, #536870914	@ 0x20000002
47f32d08:	e780428e 	str	r4, [r0, lr, lsl #5]
47f32d0c:	e3a0e209 	mov	lr, #-1879048192	@ 0x90000000
47f32d10:	e3a00001 	mov	r0, #1
47f32d14:	e5834010 	str	r4, [r3, #16]
47f32d18:	e9835001 	stmib	r3, {r0, r12, lr}
47f32d1c:	e1a00001 	mov	r0, r1
47f32d20:	e5834014 	str	r4, [r3, #20]
47f32d24:	e1a01002 	mov	r1, r2
47f32d28:	e5834018 	str	r4, [r3, #24]
47f32d2c:	e1a02003 	mov	r2, r3
47f32d30:	e583401c 	str	r4, [r3, #28]
47f32d34:	ebffff7c 	bl	0x47f32b2c
47f32d38:	e1a00004 	mov	r0, r4
47f32d3c:	e8bd8010 	pop	{r4, pc}
47f32d40:	47f6228c 	ldrbmi	r2, [r6, r12, lsl #5]!
47f32d44:	92164000 	andsls	r4, r6, #0
47f32d48:	47f446ca 	ldrbmi	r4, [r4, r10, asr #13]!
47f32d4c:	e59fc038 	ldr	r12, [pc, #56]	@ 0x47f32d8c
47f32d50:	e3a03000 	mov	r3, #0
47f32d54:	e1a00003 	mov	r0, r3
47f32d58:	e2832b83 	add	r2, r3, #134144	@ 0x20c00
47f32d5c:	e1a0100c 	mov	r1, r12
47f32d60:	e2822c01 	add	r2, r2, #256	@ 0x100
47f32d64:	e1a02682 	lsl	r2, r2, #13
47f32d68:	e7a12003 	str	r2, [r1, r3]!
47f32d6c:	e2833008 	add	r3, r3, #8
47f32d70:	e5810004 	str	r0, [r1, #4]
47f32d74:	e3530040 	cmp	r3, #64	@ 0x40
47f32d78:	1afffff6 	bne	0x47f32d58
47f32d7c:	e59f200c 	ldr	r2, [pc, #12]	@ 0x47f32d90
47f32d80:	e59f300c 	ldr	r3, [pc, #12]	@ 0x47f32d94
47f32d84:	e583205c 	str	r2, [r3, #92]	@ 0x5c
47f32d88:	e12fff1e 	bx	lr
47f32d8c:	47f62298 			@ <UNDEFINED> instruction: 0x47f62298
47f32d90:	41c18000 	bicmi	r8, r1, r0
47f32d94:	47f6228c 	ldrbmi	r2, [r6, r12, lsl #5]!
47f32d98:	e92d4008 	push	{r3, lr}
47f32d9c:	e3a00000 	mov	r0, #0
47f32da0:	e59f100c 	ldr	r1, [pc, #12]	@ 0x47f32db4
47f32da4:	ebfffb59 	bl	0x47f31b10
47f32da8:	ebffffe7 	bl	0x47f32d4c
47f32dac:	e3a00000 	mov	r0, #0
47f32db0:	e8bd8008 	pop	{r3, pc}
47f32db4:	47f51920 	ldrbmi	r1, [r5, r0, lsr #18]!
47f32db8:	e92d4038 	push	{r3, r4, r5, lr}
47f32dbc:	e3a00040 	mov	r0, #64	@ 0x40
47f32dc0:	ebff5fbc 	bl	0x47f0acb8
47f32dc4:	e2504000 	subs	r4, r0, #0
47f32dc8:	1a000001 	bne	0x47f32dd4
47f32dcc:	e8bd4038 	pop	{r3, r4, r5, lr}
47f32dd0:	eaff5f2e 	b	0x47f0aa90
47f32dd4:	e3a02040 	mov	r2, #64	@ 0x40
47f32dd8:	e3a01000 	mov	r1, #0
47f32ddc:	ebffce20 	bl	0x47f26664
47f32de0:	e59f3064 	ldr	r3, [pc, #100]	@ 0x47f32e4c
47f32de4:	e2845010 	add	r5, r4, #16
47f32de8:	e59f1060 	ldr	r1, [pc, #96]	@ 0x47f32e50
47f32dec:	e1a00004 	mov	r0, r4
47f32df0:	e5843020 	str	r3, [r4, #32]
47f32df4:	e59f3058 	ldr	r3, [pc, #88]	@ 0x47f32e54
47f32df8:	e584302c 	str	r3, [r4, #44]	@ 0x2c
47f32dfc:	e59f3054 	ldr	r3, [pc, #84]	@ 0x47f32e58
47f32e00:	e5843024 	str	r3, [r4, #36]	@ 0x24
47f32e04:	e59f3050 	ldr	r3, [pc, #80]	@ 0x47f32e5c
47f32e08:	e5843028 	str	r3, [r4, #40]	@ 0x28
47f32e0c:	ebffd268 	bl	0x47f277b4
47f32e10:	e59f0048 	ldr	r0, [pc, #72]	@ 0x47f32e60
47f32e14:	e1a01005 	mov	r1, r5
47f32e18:	ebffe7b3 	bl	0x47f2ccec
47f32e1c:	e3500000 	cmp	r0, #0
47f32e20:	1a000002 	bne	0x47f32e30
47f32e24:	e59f0038 	ldr	r0, [pc, #56]	@ 0x47f32e64
47f32e28:	ebff5dbe 	bl	0x47f0a528
47f32e2c:	ea000003 	b	0x47f32e40
47f32e30:	e59f0030 	ldr	r0, [pc, #48]	@ 0x47f32e68
47f32e34:	e1a01005 	mov	r1, r5
47f32e38:	e3a02006 	mov	r2, #6
47f32e3c:	ebffce28 	bl	0x47f266e4
47f32e40:	e1a00004 	mov	r0, r4
47f32e44:	e8bd4038 	pop	{r3, r4, r5, lr}
47f32e48:	eaffe88d 	b	0x47f2d084
47f32e4c:	47f327b4 			@ <UNDEFINED> instruction: 0x47f327b4
47f32e50:	47f446de 	ubfxmi	r4, lr, #13, #21
47f32e54:	47f327dc 	ubfxmi	r2, r12, #15, #20
47f32e58:	47f32c60 	ldrbmi	r2, [r3, r0, ror #24]!
47f32e5c:	47f32874 			@ <UNDEFINED> instruction: 0x47f32874
47f32e60:	47f3ae4d 	ldrbmi	r10, [r3, sp, asr #28]!
47f32e64:	47f446e3 	ldrbmi	r4, [r4, r3, ror #13]!
47f32e68:	47f51920 	ldrbmi	r1, [r5, r0, lsr #18]!
47f32e6c:	e3003a37 	movw	r3, #2615	@ 0xa37
47f32e70:	e0000093 	mul	r0, r3, r0
47f32e74:	e59f3004 	ldr	r3, [pc, #4]	@ 0x47f32e80
47f32e78:	e5830188 	str	r0, [r3, #392]	@ 0x188
47f32e7c:	e12fff1e 	bx	lr
47f32e80:	92310000 	eorsls	r0, r1, #0
47f32e84:	e59f3050 	ldr	r3, [pc, #80]	@ 0x47f32edc
47f32e88:	e3050555 	movw	r0, #21845	@ 0x5555
47f32e8c:	e59f204c 	ldr	r2, [pc, #76]	@ 0x47f32ee0
47f32e90:	e59f104c 	ldr	r1, [pc, #76]	@ 0x47f32ee4
47f32e94:	e5832004 	str	r2, [r3, #4]
47f32e98:	e59f2048 	ldr	r2, [pc, #72]	@ 0x47f32ee8
47f32e9c:	e5832340 	str	r2, [r3, #832]	@ 0x340
47f32ea0:	e3a0203f 	mov	r2, #63	@ 0x3f
47f32ea4:	e5832344 	str	r2, [r3, #836]	@ 0x344
47f32ea8:	e5832380 	str	r2, [r3, #896]	@ 0x380
47f32eac:	e583163c 	str	r1, [r3, #1596]	@ 0x63c
47f32eb0:	e3a010ff 	mov	r1, #255	@ 0xff
47f32eb4:	e58311c0 	str	r1, [r3, #448]	@ 0x1c0
47f32eb8:	e58301c4 	str	r0, [r3, #452]	@ 0x1c4
47f32ebc:	e59f0028 	ldr	r0, [pc, #40]	@ 0x47f32eec
47f32ec0:	e5830188 	str	r0, [r3, #392]	@ 0x188
47f32ec4:	e3a00000 	mov	r0, #0
47f32ec8:	e58312c0 	str	r1, [r3, #704]	@ 0x2c0
47f32ecc:	e30f1fff 	movw	r1, #65535	@ 0xffff
47f32ed0:	e5831300 	str	r1, [r3, #768]	@ 0x300
47f32ed4:	e5832304 	str	r2, [r3, #772]	@ 0x304
47f32ed8:	e12fff1e 	bx	lr
47f32edc:	92310000 	eorsls	r0, r1, #0
47f32ee0:	040200ff 	streq	r0, [r2], #-255	@ 0xffffff01
47f32ee4:	aaaaaaaa 	bge	0x469dd994
47f32ee8:	ff5555ff 			@ <UNDEFINED> instruction: 0xff5555ff
47f32eec:	000bf874 	andeq	pc, r11, r4, ror r8	@ <UNPREDICTABLE>
47f32ef0:	e3500007 	cmp	r0, #7
47f32ef4:	812fff1e 	bxhi	lr
47f32ef8:	e59f3014 	ldr	r3, [pc, #20]	@ 0x47f32f14
47f32efc:	e7933100 	ldr	r3, [r3, r0, lsl #2]
47f32f00:	e3530000 	cmp	r3, #0
47f32f04:	a7eb1051 	ubfxge	r1, r1, #0, #12
47f32f08:	a59f2008 	ldrge	r2, [pc, #8]	@ 0x47f32f18
47f32f0c:	a7821103 	strge	r1, [r2, r3, lsl #2]
47f32f10:	e12fff1e 	bx	lr
47f32f14:	47f3a7c0 	ldrbmi	r10, [r3, r0, asr #15]!
47f32f18:	92308040 	eorsls	r8, r0, #64	@ 0x40
47f32f1c:	e92d4010 	push	{r4, lr}
47f32f20:	e3a04000 	mov	r4, #0
47f32f24:	e6ef0074 	uxtb	r0, r4
47f32f28:	e3a01001 	mov	r1, #1
47f32f2c:	e2844001 	add	r4, r4, #1
47f32f30:	ebffffee 	bl	0x47f32ef0
47f32f34:	e3540008 	cmp	r4, #8
47f32f38:	1afffff9 	bne	0x47f32f24
47f32f3c:	e59f3028 	ldr	r3, [pc, #40]	@ 0x47f32f6c
47f32f40:	e3a00000 	mov	r0, #0
47f32f44:	e59f2024 	ldr	r2, [pc, #36]	@ 0x47f32f70
47f32f48:	e5832140 	str	r2, [r3, #320]	@ 0x140
47f32f4c:	e59f2020 	ldr	r2, [pc, #32]	@ 0x47f32f74
47f32f50:	e5834144 	str	r4, [r3, #324]	@ 0x144
47f32f54:	e5d22000 	ldrb	r2, [r2]
47f32f58:	e3520000 	cmp	r2, #0
47f32f5c:	15932140 	ldrne	r2, [r3, #320]	@ 0x140
47f32f60:	13822601 	orrne	r2, r2, #1048576	@ 0x100000
47f32f64:	15832140 	strne	r2, [r3, #320]	@ 0x140
47f32f68:	e8bd8010 	pop	{r4, pc}
47f32f6c:	92308000 	eorsls	r8, r0, #0
47f32f70:	80010000 	andhi	r0, r1, r0
47f32f74:	47f6219d 			@ <UNDEFINED> instruction: 0x47f6219d
47f32f78:	e1a0c001 	mov	r12, r1
47f32f7c:	e16f1f11 	clz	r1, r1
47f32f80:	e1a012a1 	lsr	r1, r1, #5
47f32f84:	e350003f 	cmp	r0, #63	@ 0x3f
47f32f88:	91a03001 	movls	r3, r1
47f32f8c:	83813001 	orrhi	r3, r1, #1
47f32f90:	e3530000 	cmp	r3, #0
47f32f94:	1a000018 	bne	0x47f32ffc
47f32f98:	e59f1064 	ldr	r1, [pc, #100]	@ 0x47f33004
47f32f9c:	e3a02005 	mov	r2, #5
47f32fa0:	e52de004 	push	{lr}		@ (str lr, [sp, #-4]!)
47f32fa4:	e591e018 	ldr	lr, [r1, #24]
47f32fa8:	e59f3054 	ldr	r3, [pc, #84]	@ 0x47f33004
47f32fac:	e31e0001 	tst	lr, #1
47f32fb0:	0a000009 	beq	0x47f32fdc
47f32fb4:	e3800502 	orr	r0, r0, #8388608	@ 0x800000
47f32fb8:	e5830014 	str	r0, [r3, #20]
47f32fbc:	e59c2008 	ldr	r2, [r12, #8]
47f32fc0:	e3a00000 	mov	r0, #0
47f32fc4:	e5832024 	str	r2, [r3, #36]	@ 0x24
47f32fc8:	e59c2004 	ldr	r2, [r12, #4]
47f32fcc:	e5832020 	str	r2, [r3, #32]
47f32fd0:	e59c2000 	ldr	r2, [r12]
47f32fd4:	e583201c 	str	r2, [r3, #28]
47f32fd8:	e49df004 	pop	{pc}		@ (ldr pc, [sp], #4)
47f32fdc:	e2522001 	subs	r2, r2, #1
47f32fe0:	1affffef 	bne	0x47f32fa4
47f32fe4:	e59f201c 	ldr	r2, [pc, #28]	@ 0x47f33008
47f32fe8:	e3e0000a 	mvn	r0, #10
47f32fec:	e5923000 	ldr	r3, [r2]
47f32ff0:	e2833001 	add	r3, r3, #1
47f32ff4:	e5823000 	str	r3, [r2]
47f32ff8:	e49df004 	pop	{pc}		@ (ldr pc, [sp], #4)
47f32ffc:	e3e00015 	mvn	r0, #21
47f33000:	e12fff1e 	bx	lr
47f33004:	92314000 	eorsls	r4, r1, #0
47f33008:	47f622ec 	ldrbmi	r2, [r6, r12, ror #5]!
47f3300c:	e1a0c001 	mov	r12, r1
47f33010:	e16f1f11 	clz	r1, r1
47f33014:	e1a012a1 	lsr	r1, r1, #5
47f33018:	e350003f 	cmp	r0, #63	@ 0x3f
47f3301c:	91a03001 	movls	r3, r1
47f33020:	83813001 	orrhi	r3, r1, #1
47f33024:	e3530000 	cmp	r3, #0
47f33028:	1a00001e 	bne	0x47f330a8
47f3302c:	e59f107c 	ldr	r1, [pc, #124]	@ 0x47f330b0
47f33030:	e3800522 	orr	r0, r0, #142606336	@ 0x8800000
47f33034:	e3a02005 	mov	r2, #5
47f33038:	e92d4010 	push	{r4, lr}
47f3303c:	e5913018 	ldr	r3, [r1, #24]
47f33040:	e3130001 	tst	r3, #1
47f33044:	15810014 	strne	r0, [r1, #20]
47f33048:	13a03005 	movne	r3, #5
47f3304c:	1a000009 	bne	0x47f33078
47f33050:	e2522001 	subs	r2, r2, #1
47f33054:	1afffff8 	bne	0x47f3303c
47f33058:	e59f2054 	ldr	r2, [pc, #84]	@ 0x47f330b4
47f3305c:	e3e0000a 	mvn	r0, #10
47f33060:	e5923000 	ldr	r3, [r2]
47f33064:	e2833001 	add	r3, r3, #1
47f33068:	e5823000 	str	r3, [r2]
47f3306c:	e8bd8010 	pop	{r4, pc}
47f33070:	e2533001 	subs	r3, r3, #1
47f33074:	0afffff5 	beq	0x47f33050
47f33078:	e5914018 	ldr	r4, [r1, #24]
47f3307c:	e59fe02c 	ldr	lr, [pc, #44]	@ 0x47f330b0
47f33080:	e3140001 	tst	r4, #1
47f33084:	0afffff9 	beq	0x47f33070
47f33088:	e59e3024 	ldr	r3, [lr, #36]	@ 0x24
47f3308c:	e3a00000 	mov	r0, #0
47f33090:	e58c3008 	str	r3, [r12, #8]
47f33094:	e59e3020 	ldr	r3, [lr, #32]
47f33098:	e58c3004 	str	r3, [r12, #4]
47f3309c:	e59e301c 	ldr	r3, [lr, #28]
47f330a0:	e58c3000 	str	r3, [r12]
47f330a4:	e8bd8010 	pop	{r4, pc}
47f330a8:	e3e00015 	mvn	r0, #21
47f330ac:	e12fff1e 	bx	lr
47f330b0:	92314000 	eorsls	r4, r1, #0
47f330b4:	47f622ec 	ldrbmi	r2, [r6, r12, ror #5]!
47f330b8:	e92d401f 	push	{r0, r1, r2, r3, r4, lr}
47f330bc:	e3a03080 	mov	r3, #128	@ 0x80
47f330c0:	e3a04000 	mov	r4, #0
47f330c4:	e98d0018 	stmib	sp, {r3, r4}
47f330c8:	e1a00004 	mov	r0, r4
47f330cc:	e28d1004 	add	r1, sp, #4
47f330d0:	ebffffa8 	bl	0x47f32f78
47f330d4:	e2502000 	subs	r2, r0, #0
47f330d8:	aa000004 	bge	0x47f330f0
47f330dc:	e59f0034 	ldr	r0, [pc, #52]	@ 0x47f33118
47f330e0:	e1a01004 	mov	r1, r4
47f330e4:	ebff5d1b 	bl	0x47f0a558
47f330e8:	e3e00000 	mvn	r0, #0
47f330ec:	ea000007 	b	0x47f33110
47f330f0:	e2844001 	add	r4, r4, #1
47f330f4:	e3540040 	cmp	r4, #64	@ 0x40
47f330f8:	1afffff2 	bne	0x47f330c8
47f330fc:	e59f3018 	ldr	r3, [pc, #24]	@ 0x47f3311c
47f33100:	e3a00000 	mov	r0, #0
47f33104:	e3a02a01 	mov	r2, #4096	@ 0x1000
47f33108:	e5832044 	str	r2, [r3, #68]	@ 0x44
47f3310c:	e5832040 	str	r2, [r3, #64]	@ 0x40
47f33110:	e28dd010 	add	sp, sp, #16
47f33114:	e8bd8010 	pop	{r4, pc}
47f33118:	47f446fb 			@ <UNDEFINED> instruction: 0x47f446fb
47f3311c:	92314000 	eorsls	r4, r1, #0
47f33120:	e3500004 	cmp	r0, #4
47f33124:	812fff1e 	bxhi	lr
47f33128:	e1a00900 	lsl	r0, r0, #18
47f3312c:	e3510002 	cmp	r1, #2
47f33130:	e2800492 	add	r0, r0, #-1845493760	@ 0x92000000
47f33134:	e2800707 	add	r0, r0, #1835008	@ 0x1c0000
47f33138:	e5903000 	ldr	r3, [r0]
47f3313c:	03c33902 	biceq	r3, r3, #32768	@ 0x8000
47f33140:	03833a02 	orreq	r3, r3, #8192	@ 0x2000
47f33144:	0a000006 	beq	0x47f33164
47f33148:	e3520000 	cmp	r2, #0
47f3314c:	03c33a02 	biceq	r3, r3, #8192	@ 0x2000
47f33150:	13833a0a 	orrne	r3, r3, #40960	@ 0xa000
47f33154:	03833902 	orreq	r3, r3, #32768	@ 0x8000
47f33158:	e3510001 	cmp	r1, #1
47f3315c:	03833901 	orreq	r3, r3, #16384	@ 0x4000
47f33160:	13c33901 	bicne	r3, r3, #16384	@ 0x4000
47f33164:	e5803000 	str	r3, [r0]
47f33168:	e12fff1e 	bx	lr
47f3316c:	e3500004 	cmp	r0, #4
47f33170:	91a00900 	lslls	r0, r0, #18
47f33174:	92800492 	addls	r0, r0, #-1845493760	@ 0x92000000
47f33178:	92800707 	addls	r0, r0, #1835008	@ 0x1c0000
47f3317c:	95903000 	ldrls	r3, [r0]
47f33180:	93833003 	orrls	r3, r3, #3
47f33184:	95803000 	strls	r3, [r0]
47f33188:	e12fff1e 	bx	lr
47f3318c:	e3500004 	cmp	r0, #4
47f33190:	e3a03000 	mov	r3, #0
47f33194:	e92d4073 	push	{r0, r1, r4, r5, r6, lr}
47f33198:	e1cd30b4 	strh	r3, [sp, #4]
47f3319c:	e1cd30b6 	strh	r3, [sp, #6]
47f331a0:	8a000095 	bhi	0x47f333fc
47f331a4:	e59f3258 	ldr	r3, [pc, #600]	@ 0x47f33404
47f331a8:	e1a04000 	mov	r4, r0
47f331ac:	e5931000 	ldr	r1, [r3]
47f331b0:	e59f2250 	ldr	r2, [pc, #592]	@ 0x47f33408
47f331b4:	e59f5250 	ldr	r5, [pc, #592]	@ 0x47f3340c
47f331b8:	e1510002 	cmp	r1, r2
47f331bc:	1a000019 	bne	0x47f33228
47f331c0:	e31000fb 	tst	r0, #251	@ 0xfb
47f331c4:	1a000017 	bne	0x47f33228
47f331c8:	e3a0101e 	mov	r1, #30
47f331cc:	e28d2006 	add	r2, sp, #6
47f331d0:	e7d50004 	ldrb	r0, [r5, r4]
47f331d4:	ebffb337 	bl	0x47f1feb8
47f331d8:	e3a0101e 	mov	r1, #30
47f331dc:	e3a02000 	mov	r2, #0
47f331e0:	e7d50004 	ldrb	r0, [r5, r4]
47f331e4:	ebffb36f 	bl	0x47f1ffa8
47f331e8:	e3a0101a 	mov	r1, #26
47f331ec:	e28d2004 	add	r2, sp, #4
47f331f0:	e7d50004 	ldrb	r0, [r5, r4]
47f331f4:	ebffb32f 	bl	0x47f1feb8
47f331f8:	e3a0101a 	mov	r1, #26
47f331fc:	e28d2004 	add	r2, sp, #4
47f33200:	e7d50004 	ldrb	r0, [r5, r4]
47f33204:	ebffb32b 	bl	0x47f1feb8
47f33208:	e7d50004 	ldrb	r0, [r5, r4]
47f3320c:	e3a0101e 	mov	r1, #30
47f33210:	e1dd20b6 	ldrh	r2, [sp, #6]
47f33214:	ebffb363 	bl	0x47f1ffa8
47f33218:	e1dd30b4 	ldrh	r3, [sp, #4]
47f3321c:	e3130040 	tst	r3, #64	@ 0x40
47f33220:	0a000075 	beq	0x47f333fc
47f33224:	ea000004 	b	0x47f3323c
47f33228:	e5932000 	ldr	r2, [r3]
47f3322c:	e59f31dc 	ldr	r3, [pc, #476]	@ 0x47f33410
47f33230:	e1520003 	cmp	r2, r3
47f33234:	1a000024 	bne	0x47f332cc
47f33238:	eaffffe2 	b	0x47f331c8
47f3323c:	e59f11d0 	ldr	r1, [pc, #464]	@ 0x47f33414
47f33240:	e1a02084 	lsl	r2, r4, #1
47f33244:	e2033d0e 	and	r3, r3, #896	@ 0x380
47f33248:	e1cd30b4 	strh	r3, [sp, #4]
47f3324c:	e19120b2 	ldrh	r2, [r1, r2]
47f33250:	e1520003 	cmp	r2, r3
47f33254:	1a000002 	bne	0x47f33264
47f33258:	e1a00004 	mov	r0, r4
47f3325c:	ebffffc2 	bl	0x47f3316c
47f33260:	ea000065 	b	0x47f333fc
47f33264:	e1a033a3 	lsr	r3, r3, #7
47f33268:	e3530001 	cmp	r3, #1
47f3326c:	e1a02003 	mov	r2, r3
47f33270:	93a05000 	movls	r5, #0
47f33274:	9a000007 	bls	0x47f33298
47f33278:	e2431002 	sub	r1, r3, #2
47f3327c:	e3510001 	cmp	r1, #1
47f33280:	93a05001 	movls	r5, #1
47f33284:	9a000003 	bls	0x47f33298
47f33288:	e2431004 	sub	r1, r3, #4
47f3328c:	e3510001 	cmp	r1, #1
47f33290:	83a05000 	movhi	r5, #0
47f33294:	93a05002 	movls	r5, #2
47f33298:	e2133005 	ands	r3, r3, #5
47f3329c:	03a01001 	moveq	r1, #1
47f332a0:	13a01000 	movne	r1, #0
47f332a4:	e3520004 	cmp	r2, #4
47f332a8:	03811001 	orreq	r1, r1, #1
47f332ac:	e3510000 	cmp	r1, #0
47f332b0:	13a06000 	movne	r6, #0
47f332b4:	1a00001a 	bne	0x47f33324
47f332b8:	e3530001 	cmp	r3, #1
47f332bc:	13520005 	cmpne	r2, #5
47f332c0:	03a06001 	moveq	r6, #1
47f332c4:	13a06000 	movne	r6, #0
47f332c8:	ea000015 	b	0x47f33324
47f332cc:	e3a01019 	mov	r1, #25
47f332d0:	e28d2004 	add	r2, sp, #4
47f332d4:	e7d50004 	ldrb	r0, [r5, r4]
47f332d8:	ebffb2f6 	bl	0x47f1feb8
47f332dc:	e7d50004 	ldrb	r0, [r5, r4]
47f332e0:	e3a01019 	mov	r1, #25
47f332e4:	e28d2004 	add	r2, sp, #4
47f332e8:	ebffb2f2 	bl	0x47f1feb8
47f332ec:	e1dd30b4 	ldrh	r3, [sp, #4]
47f332f0:	e3130001 	tst	r3, #1
47f332f4:	0a000040 	beq	0x47f333fc
47f332f8:	e59f1114 	ldr	r1, [pc, #276]	@ 0x47f33414
47f332fc:	e1a02084 	lsl	r2, r4, #1
47f33300:	e203300e 	and	r3, r3, #14
47f33304:	e1cd30b4 	strh	r3, [sp, #4]
47f33308:	e19120b2 	ldrh	r2, [r1, r2]
47f3330c:	e1520003 	cmp	r2, r3
47f33310:	0affffd0 	beq	0x47f33258
47f33314:	e7e150d3 	ubfx	r5, r3, #1, #2
47f33318:	e3550003 	cmp	r5, #3
47f3331c:	0a000036 	beq	0x47f333fc
47f33320:	e1a061a3 	lsr	r6, r3, #3
47f33324:	e59f30ec 	ldr	r3, [pc, #236]	@ 0x47f33418
47f33328:	e1a01004 	mov	r1, r4
47f3332c:	e59f00e8 	ldr	r0, [pc, #232]	@ 0x47f3341c
47f33330:	e083c106 	add	r12, r3, r6, lsl #2
47f33334:	e7932105 	ldr	r2, [r3, r5, lsl #2]
47f33338:	e59c3010 	ldr	r3, [r12, #16]
47f3333c:	ebff5c85 	bl	0x47f0a558
47f33340:	e2843006 	add	r3, r4, #6
47f33344:	e3a00001 	mov	r0, #1
47f33348:	e1a00310 	lsl	r0, r0, r3
47f3334c:	ebfffa1e 	bl	0x47f31bcc
47f33350:	e1a00904 	lsl	r0, r4, #18
47f33354:	e59f30c4 	ldr	r3, [pc, #196]	@ 0x47f33420
47f33358:	e2800492 	add	r0, r0, #-1845493760	@ 0x92000000
47f3335c:	e2800707 	add	r0, r0, #1835008	@ 0x1c0000
47f33360:	e3a02106 	mov	r2, #-2147483647	@ 0x80000001
47f33364:	e5803000 	str	r3, [r0]
47f33368:	e59f30b4 	ldr	r3, [pc, #180]	@ 0x47f33424
47f3336c:	e59f00b4 	ldr	r0, [pc, #180]	@ 0x47f33428
47f33370:	e7832904 	str	r2, [r3, r4, lsl #18]
47f33374:	e2833e36 	add	r3, r3, #864	@ 0x360
47f33378:	e59f20ac 	ldr	r2, [pc, #172]	@ 0x47f3342c
47f3337c:	e7832904 	str	r2, [r3, r4, lsl #18]
47f33380:	e2833dc2 	add	r3, r3, #12416	@ 0x3080
47f33384:	e3a02032 	mov	r2, #50	@ 0x32
47f33388:	e7832904 	str	r2, [r3, r4, lsl #18]
47f3338c:	e28330c0 	add	r3, r3, #192	@ 0xc0
47f33390:	e3a020a8 	mov	r2, #168	@ 0xa8
47f33394:	e7832904 	str	r2, [r3, r4, lsl #18]
47f33398:	e2433dd2 	sub	r3, r3, #13440	@ 0x3480
47f3339c:	e2433030 	sub	r3, r3, #48	@ 0x30
47f333a0:	e30f2ffe 	movw	r2, #65534	@ 0xfffe
47f333a4:	e7832904 	str	r2, [r3, r4, lsl #18]
47f333a8:	e2833e1b 	add	r3, r3, #432	@ 0x1b0
47f333ac:	e59f207c 	ldr	r2, [pc, #124]	@ 0x47f33430
47f333b0:	e7832904 	str	r2, [r3, r4, lsl #18]
47f333b4:	e2833e11 	add	r3, r3, #272	@ 0x110
47f333b8:	e3a02901 	mov	r2, #16384	@ 0x4000
47f333bc:	e7832904 	str	r2, [r3, r4, lsl #18]
47f333c0:	e2833c29 	add	r3, r3, #10496	@ 0x2900
47f333c4:	e59f2068 	ldr	r2, [pc, #104]	@ 0x47f33434
47f333c8:	e2833030 	add	r3, r3, #48	@ 0x30
47f333cc:	e7832904 	str	r2, [r3, r4, lsl #18]
47f333d0:	ebff5c60 	bl	0x47f0a558
47f333d4:	e1a00004 	mov	r0, r4
47f333d8:	e1a02006 	mov	r2, r6
47f333dc:	e1a01005 	mov	r1, r5
47f333e0:	ebffff4e 	bl	0x47f33120
47f333e4:	e1a00004 	mov	r0, r4
47f333e8:	ebffff5f 	bl	0x47f3316c
47f333ec:	e1dd20b4 	ldrh	r2, [sp, #4]
47f333f0:	e59f301c 	ldr	r3, [pc, #28]	@ 0x47f33414
47f333f4:	e1a04084 	lsl	r4, r4, #1
47f333f8:	e18320b4 	strh	r2, [r3, r4]
47f333fc:	e28dd008 	add	sp, sp, #8
47f33400:	e8bd8070 	pop	{r4, r5, r6, pc}
47f33404:	92040000 	andls	r0, r4, #0
47f33408:	27912700 	ldrcs	r2, [r1, r0, lsl #14]
47f3340c:	47f47411 			@ <UNDEFINED> instruction: 0x47f47411
47f33410:	27912800 	ldrcs	r2, [r1, r0, lsl #16]
47f33414:	47f622f4 			@ <UNDEFINED> instruction: 0x47f622f4
47f33418:	47f3a7e0 	ldrbmi	r10, [r3, r0, ror #15]!
47f3341c:	47f44718 			@ <UNDEFINED> instruction: 0x47f44718
47f33420:	00bbe003 	adcseq	lr, r11, r3
47f33424:	921c0020 	andsls	r0, r12, #32
47f33428:	47f4473a 			@ <UNDEFINED> instruction: 0x47f4473a
47f3342c:	00011200 	andeq	r1, r1, r0, lsl #4
47f33430:	00300002 	eorseq	r0, r0, r2
47f33434:	0010ff11 	andseq	pc, r0, r1, lsl pc	@ <UNPREDICTABLE>
47f33438:	e3500004 	cmp	r0, #4
47f3343c:	91a00900 	lslls	r0, r0, #18
47f33440:	92800492 	addls	r0, r0, #-1845493760	@ 0x92000000
47f33444:	92800707 	addls	r0, r0, #1835008	@ 0x1c0000
47f33448:	95903000 	ldrls	r3, [r0]
47f3344c:	93c33001 	bicls	r3, r3, #1
47f33450:	95803000 	strls	r3, [r0]
47f33454:	e12fff1e 	bx	lr
47f33458:	e59f301c 	ldr	r3, [pc, #28]	@ 0x47f3347c
47f3345c:	e59f101c 	ldr	r1, [pc, #28]	@ 0x47f33480
47f33460:	e5932000 	ldr	r2, [r3]
47f33464:	e3c22003 	bic	r2, r2, #3
47f33468:	e5832000 	str	r2, [r3]
47f3346c:	e2833701 	add	r3, r3, #262144	@ 0x40000
47f33470:	e1530001 	cmp	r3, r1
47f33474:	1afffff9 	bne	0x47f33460
47f33478:	e12fff1e 	bx	lr
47f3347c:	921c0000 	andsls	r0, r12, #0
47f33480:	92300000 	eorsls	r0, r0, #0
47f33484:	e59f301c 	ldr	r3, [pc, #28]	@ 0x47f334a8
47f33488:	e3e02000 	mvn	r2, #0
47f3348c:	e3a00000 	mov	r0, #0
47f33490:	e1c320b0 	strh	r2, [r3]
47f33494:	e1c320b2 	strh	r2, [r3, #2]
47f33498:	e1c320b4 	strh	r2, [r3, #4]
47f3349c:	e1c320b6 	strh	r2, [r3, #6]
47f334a0:	e1c320b8 	strh	r2, [r3, #8]
47f334a4:	e12fff1e 	bx	lr
47f334a8:	47f622f4 			@ <UNDEFINED> instruction: 0x47f622f4
47f334ac:	e59f3008 	ldr	r3, [pc, #8]	@ 0x47f334bc
47f334b0:	e3a02001 	mov	r2, #1
47f334b4:	e5832000 	str	r2, [r3]
47f334b8:	e12fff1e 	bx	lr
47f334bc:	92304000 	eorsls	r4, r0, #0
47f334c0:	e92d4010 	push	{r4, lr}
47f334c4:	e3e03000 	mvn	r3, #0
47f334c8:	e59f4028 	ldr	r4, [pc, #40]	@ 0x47f334f8
47f334cc:	e3a00ffa 	mov	r0, #1000	@ 0x3e8
47f334d0:	e5843008 	str	r3, [r4, #8]
47f334d4:	ebffcd06 	bl	0x47f268f4
47f334d8:	ebfffe8f 	bl	0x47f32f1c
47f334dc:	ebfffe68 	bl	0x47f32e84
47f334e0:	ebfffef4 	bl	0x47f330b8
47f334e4:	ebffffe6 	bl	0x47f33484
47f334e8:	ebffffef 	bl	0x47f334ac
47f334ec:	e3a00000 	mov	r0, #0
47f334f0:	e5840050 	str	r0, [r4, #80]	@ 0x50
47f334f4:	e8bd8010 	pop	{r4, pc}
47f334f8:	9232c000 	eorsls	r12, r2, #0
47f334fc:	e280049f 	add	r0, r0, #-1627389952	@ 0x9f000000
47f33500:	e280060e 	add	r0, r0, #14680064	@ 0xe00000
47f33504:	e5801000 	str	r1, [r0]
47f33508:	e12fff1e 	bx	lr
47f3350c:	e280049f 	add	r0, r0, #-1627389952	@ 0x9f000000
47f33510:	e280060e 	add	r0, r0, #14680064	@ 0xe00000
47f33514:	e5900000 	ldr	r0, [r0]
47f33518:	e12fff1e 	bx	lr
47f3351c:	e280049f 	add	r0, r0, #-1627389952	@ 0x9f000000
47f33520:	e280060e 	add	r0, r0, #14680064	@ 0xe00000
47f33524:	e52de004 	push	{lr}		@ (str lr, [sp, #-4]!)
47f33528:	e3e0e000 	mvn	lr, #0
47f3352c:	e590c000 	ldr	r12, [r0]
47f33530:	e1e0221e 	mvn	r2, lr, lsl r2
47f33534:	e1ccc312 	bic	r12, r12, r2, lsl r3
47f33538:	e18c1311 	orr	r1, r12, r1, lsl r3
47f3353c:	e5801000 	str	r1, [r0]
47f33540:	e49df004 	pop	{pc}		@ (ldr pc, [sp], #4)
47f33544:	e92d401f 	push	{r0, r1, r2, r3, r4, lr}
47f33548:	e58d000c 	str	r0, [sp, #12]
47f3354c:	e58d1008 	str	r1, [sp, #8]
47f33550:	e58d2004 	str	r2, [sp, #4]
47f33554:	e58d3000 	str	r3, [sp]
47f33558:	e59d3004 	ldr	r3, [sp, #4]
47f3355c:	e353000f 	cmp	r3, #15
47f33560:	8a000002 	bhi	0x47f33570
47f33564:	e59d1004 	ldr	r1, [sp, #4]
47f33568:	e59f0244 	ldr	r0, [pc, #580]	@ 0x47f337b4
47f3356c:	ebff5bf9 	bl	0x47f0a558
47f33570:	e59f3240 	ldr	r3, [pc, #576]	@ 0x47f337b8
47f33574:	e5932000 	ldr	r2, [r3]
47f33578:	e59f423c 	ldr	r4, [pc, #572]	@ 0x47f337bc
47f3357c:	e1520004 	cmp	r2, r4
47f33580:	1a000027 	bne	0x47f33624
47f33584:	e59d200c 	ldr	r2, [sp, #12]
47f33588:	e59d300c 	ldr	r3, [sp, #12]
47f3358c:	e5933000 	ldr	r3, [r3]
47f33590:	e3833102 	orr	r3, r3, #-2147483648	@ 0x80000000
47f33594:	e5823000 	str	r3, [r2]
47f33598:	e59d200c 	ldr	r2, [sp, #12]
47f3359c:	e59d300c 	ldr	r3, [sp, #12]
47f335a0:	e5933000 	ldr	r3, [r3]
47f335a4:	e3833302 	orr	r3, r3, #134217728	@ 0x8000000
47f335a8:	e5823000 	str	r3, [r2]
47f335ac:	e59d200c 	ldr	r2, [sp, #12]
47f335b0:	e59d300c 	ldr	r3, [sp, #12]
47f335b4:	e5933000 	ldr	r3, [r3]
47f335b8:	e3c33401 	bic	r3, r3, #16777216	@ 0x1000000
47f335bc:	e5823000 	str	r3, [r2]
47f335c0:	e59d200c 	ldr	r2, [sp, #12]
47f335c4:	e59d300c 	ldr	r3, [sp, #12]
47f335c8:	e5933000 	ldr	r3, [r3]
47f335cc:	e59d1008 	ldr	r1, [sp, #8]
47f335d0:	e3c3373f 	bic	r3, r3, #16515072	@ 0xfc0000
47f335d4:	e1833901 	orr	r3, r3, r1, lsl #18
47f335d8:	e5823000 	str	r3, [r2]
47f335dc:	e59d100c 	ldr	r1, [sp, #12]
47f335e0:	e59d300c 	ldr	r3, [sp, #12]
47f335e4:	e5932000 	ldr	r2, [r3]
47f335e8:	e59d0004 	ldr	r0, [sp, #4]
47f335ec:	e3c23bff 	bic	r3, r2, #261120	@ 0x3fc00
47f335f0:	e3c33d0f 	bic	r3, r3, #960	@ 0x3c0
47f335f4:	e1833300 	orr	r3, r3, r0, lsl #6
47f335f8:	e5813000 	str	r3, [r1]
47f335fc:	e59d3000 	ldr	r3, [sp]
47f33600:	e3530000 	cmp	r3, #0
47f33604:	0a000032 	beq	0x47f336d4
47f33608:	e59d200c 	ldr	r2, [sp, #12]
47f3360c:	e59d300c 	ldr	r3, [sp, #12]
47f33610:	e5933000 	ldr	r3, [r3]
47f33614:	e59d1000 	ldr	r1, [sp]
47f33618:	e3c33038 	bic	r3, r3, #56	@ 0x38
47f3361c:	e1833181 	orr	r3, r3, r1, lsl #3
47f33620:	ea00002a 	b	0x47f336d0
47f33624:	e5932000 	ldr	r2, [r3]
47f33628:	e59f3190 	ldr	r3, [pc, #400]	@ 0x47f337c0
47f3362c:	e1520003 	cmp	r2, r3
47f33630:	1a000031 	bne	0x47f336fc
47f33634:	e59d200c 	ldr	r2, [sp, #12]
47f33638:	e59d300c 	ldr	r3, [sp, #12]
47f3363c:	e5933000 	ldr	r3, [r3]
47f33640:	e3833101 	orr	r3, r3, #1073741824	@ 0x40000000
47f33644:	e5823000 	str	r3, [r2]
47f33648:	e59d200c 	ldr	r2, [sp, #12]
47f3364c:	e59d300c 	ldr	r3, [sp, #12]
47f33650:	e5933000 	ldr	r3, [r3]
47f33654:	e3833202 	orr	r3, r3, #536870912	@ 0x20000000
47f33658:	e5823000 	str	r3, [r2]
47f3365c:	e59d200c 	ldr	r2, [sp, #12]
47f33660:	e59d300c 	ldr	r3, [sp, #12]
47f33664:	e5933000 	ldr	r3, [r3]
47f33668:	e3c33201 	bic	r3, r3, #268435456	@ 0x10000000
47f3366c:	e5823000 	str	r3, [r2]
47f33670:	e59d200c 	ldr	r2, [sp, #12]
47f33674:	e59d300c 	ldr	r3, [sp, #12]
47f33678:	e5933000 	ldr	r3, [r3]
47f3367c:	e59d1008 	ldr	r1, [sp, #8]
47f33680:	e3c3363f 	bic	r3, r3, #66060288	@ 0x3f00000
47f33684:	e1833a01 	orr	r3, r3, r1, lsl #20
47f33688:	e5823000 	str	r3, [r2]
47f3368c:	e59d100c 	ldr	r1, [sp, #12]
47f33690:	e59d300c 	ldr	r3, [sp, #12]
47f33694:	e5932000 	ldr	r2, [r3]
47f33698:	e59d0004 	ldr	r0, [sp, #4]
47f3369c:	e3c23aff 	bic	r3, r2, #1044480	@ 0xff000
47f336a0:	e3c33c0f 	bic	r3, r3, #3840	@ 0xf00
47f336a4:	e1833400 	orr	r3, r3, r0, lsl #8
47f336a8:	e5813000 	str	r3, [r1]
47f336ac:	e59d3000 	ldr	r3, [sp]
47f336b0:	e3530000 	cmp	r3, #0
47f336b4:	0a000006 	beq	0x47f336d4
47f336b8:	e59d200c 	ldr	r2, [sp, #12]
47f336bc:	e59d300c 	ldr	r3, [sp, #12]
47f336c0:	e5933000 	ldr	r3, [r3]
47f336c4:	e59d1000 	ldr	r1, [sp]
47f336c8:	e3c33070 	bic	r3, r3, #112	@ 0x70
47f336cc:	e1833201 	orr	r3, r3, r1, lsl #4
47f336d0:	e5823000 	str	r3, [r2]
47f336d4:	e59d3018 	ldr	r3, [sp, #24]
47f336d8:	e3530000 	cmp	r3, #0
47f336dc:	0a000006 	beq	0x47f336fc
47f336e0:	e59d100c 	ldr	r1, [sp, #12]
47f336e4:	e59d300c 	ldr	r3, [sp, #12]
47f336e8:	e5933000 	ldr	r3, [r3]
47f336ec:	e59d2018 	ldr	r2, [sp, #24]
47f336f0:	e3c33007 	bic	r3, r3, #7
47f336f4:	e1833002 	orr	r3, r3, r2
47f336f8:	e5813000 	str	r3, [r1]
47f336fc:	e59d200c 	ldr	r2, [sp, #12]
47f33700:	e3a00064 	mov	r0, #100	@ 0x64
47f33704:	e59d300c 	ldr	r3, [sp, #12]
47f33708:	e5933004 	ldr	r3, [r3, #4]
47f3370c:	e3c33302 	bic	r3, r3, #134217728	@ 0x8000000
47f33710:	e5823004 	str	r3, [r2, #4]
47f33714:	e59d200c 	ldr	r2, [sp, #12]
47f33718:	e59d300c 	ldr	r3, [sp, #12]
47f3371c:	e5933004 	ldr	r3, [r3, #4]
47f33720:	e3833301 	orr	r3, r3, #67108864	@ 0x4000000
47f33724:	e5823004 	str	r3, [r2, #4]
47f33728:	e59d200c 	ldr	r2, [sp, #12]
47f3372c:	e59d300c 	ldr	r3, [sp, #12]
47f33730:	e5933004 	ldr	r3, [r3, #4]
47f33734:	e3c33402 	bic	r3, r3, #33554432	@ 0x2000000
47f33738:	e5823004 	str	r3, [r2, #4]
47f3373c:	e59d200c 	ldr	r2, [sp, #12]
47f33740:	e59d300c 	ldr	r3, [sp, #12]
47f33744:	e5933004 	ldr	r3, [r3, #4]
47f33748:	e3c33401 	bic	r3, r3, #16777216	@ 0x1000000
47f3374c:	e5823004 	str	r3, [r2, #4]
47f33750:	e59d200c 	ldr	r2, [sp, #12]
47f33754:	e59d300c 	ldr	r3, [sp, #12]
47f33758:	e5933004 	ldr	r3, [r3, #4]
47f3375c:	e20334ff 	and	r3, r3, #-16777216	@ 0xff000000
47f33760:	e5823004 	str	r3, [r2, #4]
47f33764:	ebffcc6e 	bl	0x47f26924
47f33768:	e59f3048 	ldr	r3, [pc, #72]	@ 0x47f337b8
47f3376c:	e5932000 	ldr	r2, [r3]
47f33770:	e1520004 	cmp	r2, r4
47f33774:	059d200c 	ldreq	r2, [sp, #12]
47f33778:	059d300c 	ldreq	r3, [sp, #12]
47f3377c:	05933000 	ldreq	r3, [r3]
47f33780:	03c33102 	biceq	r3, r3, #-2147483648	@ 0x80000000
47f33784:	0a000007 	beq	0x47f337a8
47f33788:	e5932000 	ldr	r2, [r3]
47f3378c:	e59f302c 	ldr	r3, [pc, #44]	@ 0x47f337c0
47f33790:	e1520003 	cmp	r2, r3
47f33794:	1a000004 	bne	0x47f337ac
47f33798:	e59d200c 	ldr	r2, [sp, #12]
47f3379c:	e59d300c 	ldr	r3, [sp, #12]
47f337a0:	e5933000 	ldr	r3, [r3]
47f337a4:	e3c33101 	bic	r3, r3, #1073741824	@ 0x40000000
47f337a8:	e5823000 	str	r3, [r2]
47f337ac:	e28dd010 	add	sp, sp, #16
47f337b0:	e8bd8010 	pop	{r4, pc}
47f337b4:	47f44771 			@ <UNDEFINED> instruction: 0x47f44771
47f337b8:	92040000 	andls	r0, r4, #0
47f337bc:	27912810 			@ <UNDEFINED> instruction: 0x27912810
47f337c0:	27912710 			@ <UNDEFINED> instruction: 0x27912710
47f337c4:	e92d401f 	push	{r0, r1, r2, r3, r4, lr}
47f337c8:	e58d000c 	str	r0, [sp, #12]
47f337cc:	e59f0270 	ldr	r0, [pc, #624]	@ 0x47f33a44
47f337d0:	e58d1008 	str	r1, [sp, #8]
47f337d4:	e58d2004 	str	r2, [sp, #4]
47f337d8:	e58d3000 	str	r3, [sp]
47f337dc:	ebff5b5d 	bl	0x47f0a558
47f337e0:	e59d3004 	ldr	r3, [sp, #4]
47f337e4:	e3530013 	cmp	r3, #19
47f337e8:	8a000002 	bhi	0x47f337f8
47f337ec:	e59d1004 	ldr	r1, [sp, #4]
47f337f0:	e59f0250 	ldr	r0, [pc, #592]	@ 0x47f33a48
47f337f4:	ebff5b57 	bl	0x47f0a558
47f337f8:	e59f324c 	ldr	r3, [pc, #588]	@ 0x47f33a4c
47f337fc:	e5932000 	ldr	r2, [r3]
47f33800:	e59f4248 	ldr	r4, [pc, #584]	@ 0x47f33a50
47f33804:	e1520004 	cmp	r2, r4
47f33808:	1a000027 	bne	0x47f338ac
47f3380c:	e59d200c 	ldr	r2, [sp, #12]
47f33810:	e59d300c 	ldr	r3, [sp, #12]
47f33814:	e5933000 	ldr	r3, [r3]
47f33818:	e3833102 	orr	r3, r3, #-2147483648	@ 0x80000000
47f3381c:	e5823000 	str	r3, [r2]
47f33820:	e59d200c 	ldr	r2, [sp, #12]
47f33824:	e59d300c 	ldr	r3, [sp, #12]
47f33828:	e5933000 	ldr	r3, [r3]
47f3382c:	e3c33302 	bic	r3, r3, #134217728	@ 0x8000000
47f33830:	e5823000 	str	r3, [r2]
47f33834:	e59d200c 	ldr	r2, [sp, #12]
47f33838:	e59d300c 	ldr	r3, [sp, #12]
47f3383c:	e5933000 	ldr	r3, [r3]
47f33840:	e3c33401 	bic	r3, r3, #16777216	@ 0x1000000
47f33844:	e5823000 	str	r3, [r2]
47f33848:	e59d200c 	ldr	r2, [sp, #12]
47f3384c:	e59d300c 	ldr	r3, [sp, #12]
47f33850:	e5933000 	ldr	r3, [r3]
47f33854:	e59d1008 	ldr	r1, [sp, #8]
47f33858:	e3c3373f 	bic	r3, r3, #16515072	@ 0xfc0000
47f3385c:	e1833901 	orr	r3, r3, r1, lsl #18
47f33860:	e5823000 	str	r3, [r2]
47f33864:	e59d100c 	ldr	r1, [sp, #12]
47f33868:	e59d300c 	ldr	r3, [sp, #12]
47f3386c:	e5932000 	ldr	r2, [r3]
47f33870:	e59d0004 	ldr	r0, [sp, #4]
47f33874:	e3c23bff 	bic	r3, r2, #261120	@ 0x3fc00
47f33878:	e3c33d0f 	bic	r3, r3, #960	@ 0x3c0
47f3387c:	e1833300 	orr	r3, r3, r0, lsl #6
47f33880:	e5813000 	str	r3, [r1]
47f33884:	e59d3018 	ldr	r3, [sp, #24]
47f33888:	e3530000 	cmp	r3, #0
47f3388c:	0a000032 	beq	0x47f3395c
47f33890:	e59d200c 	ldr	r2, [sp, #12]
47f33894:	e59d300c 	ldr	r3, [sp, #12]
47f33898:	e5933000 	ldr	r3, [r3]
47f3389c:	e59d1018 	ldr	r1, [sp, #24]
47f338a0:	e3c33038 	bic	r3, r3, #56	@ 0x38
47f338a4:	e1833181 	orr	r3, r3, r1, lsl #3
47f338a8:	ea00002a 	b	0x47f33958
47f338ac:	e5932000 	ldr	r2, [r3]
47f338b0:	e59f319c 	ldr	r3, [pc, #412]	@ 0x47f33a54
47f338b4:	e1520003 	cmp	r2, r3
47f338b8:	1a000031 	bne	0x47f33984
47f338bc:	e59d200c 	ldr	r2, [sp, #12]
47f338c0:	e59d300c 	ldr	r3, [sp, #12]
47f338c4:	e5933000 	ldr	r3, [r3]
47f338c8:	e3833101 	orr	r3, r3, #1073741824	@ 0x40000000
47f338cc:	e5823000 	str	r3, [r2]
47f338d0:	e59d200c 	ldr	r2, [sp, #12]
47f338d4:	e59d300c 	ldr	r3, [sp, #12]
47f338d8:	e5933000 	ldr	r3, [r3]
47f338dc:	e3c33202 	bic	r3, r3, #536870912	@ 0x20000000
47f338e0:	e5823000 	str	r3, [r2]
47f338e4:	e59d200c 	ldr	r2, [sp, #12]
47f338e8:	e59d300c 	ldr	r3, [sp, #12]
47f338ec:	e5933000 	ldr	r3, [r3]
47f338f0:	e3c33201 	bic	r3, r3, #268435456	@ 0x10000000
47f338f4:	e5823000 	str	r3, [r2]
47f338f8:	e59d200c 	ldr	r2, [sp, #12]
47f338fc:	e59d300c 	ldr	r3, [sp, #12]
47f33900:	e5933000 	ldr	r3, [r3]
47f33904:	e59d1008 	ldr	r1, [sp, #8]
47f33908:	e3c3363f 	bic	r3, r3, #66060288	@ 0x3f00000
47f3390c:	e1833a01 	orr	r3, r3, r1, lsl #20
47f33910:	e5823000 	str	r3, [r2]
47f33914:	e59d100c 	ldr	r1, [sp, #12]
47f33918:	e59d300c 	ldr	r3, [sp, #12]
47f3391c:	e5932000 	ldr	r2, [r3]
47f33920:	e59d0004 	ldr	r0, [sp, #4]
47f33924:	e3c23aff 	bic	r3, r2, #1044480	@ 0xff000
47f33928:	e3c33c0f 	bic	r3, r3, #3840	@ 0xf00
47f3392c:	e1833400 	orr	r3, r3, r0, lsl #8
47f33930:	e5813000 	str	r3, [r1]
47f33934:	e59d3018 	ldr	r3, [sp, #24]
47f33938:	e3530000 	cmp	r3, #0
47f3393c:	0a000006 	beq	0x47f3395c
47f33940:	e59d200c 	ldr	r2, [sp, #12]
47f33944:	e59d300c 	ldr	r3, [sp, #12]
47f33948:	e5933000 	ldr	r3, [r3]
47f3394c:	e59d1018 	ldr	r1, [sp, #24]
47f33950:	e3c33070 	bic	r3, r3, #112	@ 0x70
47f33954:	e1833201 	orr	r3, r3, r1, lsl #4
47f33958:	e5823000 	str	r3, [r2]
47f3395c:	e59d301c 	ldr	r3, [sp, #28]
47f33960:	e3530000 	cmp	r3, #0
47f33964:	0a000006 	beq	0x47f33984
47f33968:	e59d100c 	ldr	r1, [sp, #12]
47f3396c:	e59d300c 	ldr	r3, [sp, #12]
47f33970:	e5933000 	ldr	r3, [r3]
47f33974:	e59d201c 	ldr	r2, [sp, #28]
47f33978:	e3c33007 	bic	r3, r3, #7
47f3397c:	e1833002 	orr	r3, r3, r2
47f33980:	e5813000 	str	r3, [r1]
47f33984:	e59d200c 	ldr	r2, [sp, #12]
47f33988:	e3a00064 	mov	r0, #100	@ 0x64
47f3398c:	e59d300c 	ldr	r3, [sp, #12]
47f33990:	e5933004 	ldr	r3, [r3, #4]
47f33994:	e3c33302 	bic	r3, r3, #134217728	@ 0x8000000
47f33998:	e5823004 	str	r3, [r2, #4]
47f3399c:	e59d200c 	ldr	r2, [sp, #12]
47f339a0:	e59d300c 	ldr	r3, [sp, #12]
47f339a4:	e5933004 	ldr	r3, [r3, #4]
47f339a8:	e3833301 	orr	r3, r3, #67108864	@ 0x4000000
47f339ac:	e5823004 	str	r3, [r2, #4]
47f339b0:	e59d200c 	ldr	r2, [sp, #12]
47f339b4:	e59d300c 	ldr	r3, [sp, #12]
47f339b8:	e5933004 	ldr	r3, [r3, #4]
47f339bc:	e3c33402 	bic	r3, r3, #33554432	@ 0x2000000
47f339c0:	e5823004 	str	r3, [r2, #4]
47f339c4:	e59d200c 	ldr	r2, [sp, #12]
47f339c8:	e59d300c 	ldr	r3, [sp, #12]
47f339cc:	e5933004 	ldr	r3, [r3, #4]
47f339d0:	e3c33401 	bic	r3, r3, #16777216	@ 0x1000000
47f339d4:	e5823004 	str	r3, [r2, #4]
47f339d8:	e59d100c 	ldr	r1, [sp, #12]
47f339dc:	e59d300c 	ldr	r3, [sp, #12]
47f339e0:	e5933004 	ldr	r3, [r3, #4]
47f339e4:	e59d2000 	ldr	r2, [sp]
47f339e8:	e20334ff 	and	r3, r3, #-16777216	@ 0xff000000
47f339ec:	e1833002 	orr	r3, r3, r2
47f339f0:	e5813004 	str	r3, [r1, #4]
47f339f4:	ebffcbca 	bl	0x47f26924
47f339f8:	e59f304c 	ldr	r3, [pc, #76]	@ 0x47f33a4c
47f339fc:	e5932000 	ldr	r2, [r3]
47f33a00:	e1520004 	cmp	r2, r4
47f33a04:	059d200c 	ldreq	r2, [sp, #12]
47f33a08:	059d300c 	ldreq	r3, [sp, #12]
47f33a0c:	05933000 	ldreq	r3, [r3]
47f33a10:	03c33102 	biceq	r3, r3, #-2147483648	@ 0x80000000
47f33a14:	0a000007 	beq	0x47f33a38
47f33a18:	e5932000 	ldr	r2, [r3]
47f33a1c:	e59f3030 	ldr	r3, [pc, #48]	@ 0x47f33a54
47f33a20:	e1520003 	cmp	r2, r3
47f33a24:	1a000004 	bne	0x47f33a3c
47f33a28:	e59d200c 	ldr	r2, [sp, #12]
47f33a2c:	e59d300c 	ldr	r3, [sp, #12]
47f33a30:	e5933000 	ldr	r3, [r3]
47f33a34:	e3c33101 	bic	r3, r3, #1073741824	@ 0x40000000
47f33a38:	e5823000 	str	r3, [r2]
47f33a3c:	e28dd010 	add	sp, sp, #16
47f33a40:	e8bd8010 	pop	{r4, pc}
47f33a44:	47f44795 			@ <UNDEFINED> instruction: 0x47f44795
47f33a48:	47f447af 	ldrbmi	r4, [r4, pc, lsr #15]!
47f33a4c:	92040000 	andls	r0, r4, #0
47f33a50:	27912810 			@ <UNDEFINED> instruction: 0x27912810
47f33a54:	27912710 			@ <UNDEFINED> instruction: 0x27912710
47f33a58:	e92d401f 	push	{r0, r1, r2, r3, r4, lr}
47f33a5c:	e58d000c 	str	r0, [sp, #12]
47f33a60:	e58d1008 	str	r1, [sp, #8]
47f33a64:	e58d2004 	str	r2, [sp, #4]
47f33a68:	e58d3000 	str	r3, [sp]
47f33a6c:	e59d200c 	ldr	r2, [sp, #12]
47f33a70:	e59d300c 	ldr	r3, [sp, #12]
47f33a74:	e5933000 	ldr	r3, [r3]
47f33a78:	e3833102 	orr	r3, r3, #-2147483648	@ 0x80000000
47f33a7c:	e5823000 	str	r3, [r2]
47f33a80:	e59d200c 	ldr	r2, [sp, #12]
47f33a84:	e59d300c 	ldr	r3, [sp, #12]
47f33a88:	e5933008 	ldr	r3, [r3, #8]
47f33a8c:	e3833b02 	orr	r3, r3, #2048	@ 0x800
47f33a90:	e5823008 	str	r3, [r2, #8]
47f33a94:	e59d200c 	ldr	r2, [sp, #12]
47f33a98:	e59d300c 	ldr	r3, [sp, #12]
47f33a9c:	e5933008 	ldr	r3, [r3, #8]
47f33aa0:	e3c33002 	bic	r3, r3, #2
47f33aa4:	e5823008 	str	r3, [r2, #8]
47f33aa8:	e59d200c 	ldr	r2, [sp, #12]
47f33aac:	e59d300c 	ldr	r3, [sp, #12]
47f33ab0:	e5933000 	ldr	r3, [r3]
47f33ab4:	e59d1018 	ldr	r1, [sp, #24]
47f33ab8:	e3c33038 	bic	r3, r3, #56	@ 0x38
47f33abc:	e1833181 	orr	r3, r3, r1, lsl #3
47f33ac0:	e5823000 	str	r3, [r2]
47f33ac4:	e59d100c 	ldr	r1, [sp, #12]
47f33ac8:	e59d300c 	ldr	r3, [sp, #12]
47f33acc:	e5933000 	ldr	r3, [r3]
47f33ad0:	e59d201c 	ldr	r2, [sp, #28]
47f33ad4:	e3c33007 	bic	r3, r3, #7
47f33ad8:	e1833002 	orr	r3, r3, r2
47f33adc:	e5813000 	str	r3, [r1]
47f33ae0:	e59d200c 	ldr	r2, [sp, #12]
47f33ae4:	e59d300c 	ldr	r3, [sp, #12]
47f33ae8:	e5933000 	ldr	r3, [r3]
47f33aec:	e59d1008 	ldr	r1, [sp, #8]
47f33af0:	e3c3373f 	bic	r3, r3, #16515072	@ 0xfc0000
47f33af4:	e1833901 	orr	r3, r3, r1, lsl #18
47f33af8:	e5823000 	str	r3, [r2]
47f33afc:	e59d100c 	ldr	r1, [sp, #12]
47f33b00:	e59d300c 	ldr	r3, [sp, #12]
47f33b04:	e5932000 	ldr	r2, [r3]
47f33b08:	e59d0004 	ldr	r0, [sp, #4]
47f33b0c:	e3c23bff 	bic	r3, r2, #261120	@ 0x3fc00
47f33b10:	e3c33d0f 	bic	r3, r3, #960	@ 0x3c0
47f33b14:	e1833300 	orr	r3, r3, r0, lsl #6
47f33b18:	e5813000 	str	r3, [r1]
47f33b1c:	e59d100c 	ldr	r1, [sp, #12]
47f33b20:	e3a0000a 	mov	r0, #10
47f33b24:	e59d300c 	ldr	r3, [sp, #12]
47f33b28:	e5933004 	ldr	r3, [r3, #4]
47f33b2c:	e59d2000 	ldr	r2, [sp]
47f33b30:	e20334ff 	and	r3, r3, #-16777216	@ 0xff000000
47f33b34:	e1833002 	orr	r3, r3, r2
47f33b38:	e5813004 	str	r3, [r1, #4]
47f33b3c:	e59d200c 	ldr	r2, [sp, #12]
47f33b40:	e59d300c 	ldr	r3, [sp, #12]
47f33b44:	e5933008 	ldr	r3, [r3, #8]
47f33b48:	e3c3307c 	bic	r3, r3, #124	@ 0x7c
47f33b4c:	e3833010 	orr	r3, r3, #16
47f33b50:	e5823008 	str	r3, [r2, #8]
47f33b54:	e59d200c 	ldr	r2, [sp, #12]
47f33b58:	e59d300c 	ldr	r3, [sp, #12]
47f33b5c:	e5933008 	ldr	r3, [r3, #8]
47f33b60:	e3833001 	orr	r3, r3, #1
47f33b64:	e5823008 	str	r3, [r2, #8]
47f33b68:	e59d200c 	ldr	r2, [sp, #12]
47f33b6c:	e59d300c 	ldr	r3, [sp, #12]
47f33b70:	e5933000 	ldr	r3, [r3]
47f33b74:	e3c33302 	bic	r3, r3, #134217728	@ 0x8000000
47f33b78:	e5823000 	str	r3, [r2]
47f33b7c:	e59d200c 	ldr	r2, [sp, #12]
47f33b80:	e59d300c 	ldr	r3, [sp, #12]
47f33b84:	e5933004 	ldr	r3, [r3, #4]
47f33b88:	e3c33302 	bic	r3, r3, #134217728	@ 0x8000000
47f33b8c:	e5823004 	str	r3, [r2, #4]
47f33b90:	ebffcb63 	bl	0x47f26924
47f33b94:	e59d200c 	ldr	r2, [sp, #12]
47f33b98:	e59d300c 	ldr	r3, [sp, #12]
47f33b9c:	e3a0000a 	mov	r0, #10
47f33ba0:	e5933000 	ldr	r3, [r3]
47f33ba4:	e3c33102 	bic	r3, r3, #-2147483648	@ 0x80000000
47f33ba8:	e5823000 	str	r3, [r2]
47f33bac:	ebffcb5c 	bl	0x47f26924
47f33bb0:	e59f0008 	ldr	r0, [pc, #8]	@ 0x47f33bc0
47f33bb4:	e28dd014 	add	sp, sp, #20
47f33bb8:	e49de004 	pop	{lr}		@ (ldr lr, [sp], #4)
47f33bbc:	eaff5a65 	b	0x47f0a558
47f33bc0:	47f447d3 	ubfxmi	r4, r3, #15, #21
47f33bc4:	e92d4013 	push	{r0, r1, r4, lr}
47f33bc8:	e1a04000 	mov	r4, r0
47f33bcc:	e1a01004 	mov	r1, r4
47f33bd0:	e59f00d4 	ldr	r0, [pc, #212]	@ 0x47f33cac
47f33bd4:	ebff5a5f 	bl	0x47f0a558
47f33bd8:	e59f30d0 	ldr	r3, [pc, #208]	@ 0x47f33cb0
47f33bdc:	e5931000 	ldr	r1, [r3]
47f33be0:	e59f20cc 	ldr	r2, [pc, #204]	@ 0x47f33cb4
47f33be4:	e1510002 	cmp	r1, r2
47f33be8:	1a000014 	bne	0x47f33c40
47f33bec:	e3a02325 	mov	r2, #-1811939328	@ 0x94000000
47f33bf0:	e3c41002 	bic	r1, r4, #2
47f33bf4:	e5923050 	ldr	r3, [r2, #80]	@ 0x50
47f33bf8:	e3510001 	cmp	r1, #1
47f33bfc:	e3c33102 	bic	r3, r3, #-2147483648	@ 0x80000000
47f33c00:	e5823050 	str	r3, [r2, #80]	@ 0x50
47f33c04:	03a03002 	moveq	r3, #2
47f33c08:	059f00a8 	ldreq	r0, [pc, #168]	@ 0x47f33cb8
47f33c0c:	058d3000 	streq	r3, [sp]
47f33c10:	0a000018 	beq	0x47f33c78
47f33c14:	e59f009c 	ldr	r0, [pc, #156]	@ 0x47f33cb8
47f33c18:	e3a01005 	mov	r1, #5
47f33c1c:	e3a03003 	mov	r3, #3
47f33c20:	e88d000a 	stm	sp, {r1, r3}
47f33c24:	e3a01001 	mov	r1, #1
47f33c28:	e3a0205d 	mov	r2, #93	@ 0x5d
47f33c2c:	e59f3088 	ldr	r3, [pc, #136]	@ 0x47f33cbc
47f33c30:	ebfffee3 	bl	0x47f337c4
47f33c34:	e3a00032 	mov	r0, #50	@ 0x32
47f33c38:	ebffcb39 	bl	0x47f26924
47f33c3c:	ea000016 	b	0x47f33c9c
47f33c40:	e5932000 	ldr	r2, [r3]
47f33c44:	e59f3074 	ldr	r3, [pc, #116]	@ 0x47f33cc0
47f33c48:	e1520003 	cmp	r2, r3
47f33c4c:	1a000012 	bne	0x47f33c9c
47f33c50:	e3a02325 	mov	r2, #-1811939328	@ 0x94000000
47f33c54:	e3c41002 	bic	r1, r4, #2
47f33c58:	e5923058 	ldr	r3, [r2, #88]	@ 0x58
47f33c5c:	e3510001 	cmp	r1, #1
47f33c60:	e3c33101 	bic	r3, r3, #1073741824	@ 0x40000000
47f33c64:	e5823058 	str	r3, [r2, #88]	@ 0x58
47f33c68:	1a000006 	bne	0x47f33c88
47f33c6c:	e59f0050 	ldr	r0, [pc, #80]	@ 0x47f33cc4
47f33c70:	e3a03002 	mov	r3, #2
47f33c74:	e58d3000 	str	r3, [sp]
47f33c78:	e3a02032 	mov	r2, #50	@ 0x32
47f33c7c:	e3a03004 	mov	r3, #4
47f33c80:	ebfffe2f 	bl	0x47f33544
47f33c84:	eaffffea 	b	0x47f33c34
47f33c88:	e3a02005 	mov	r2, #5
47f33c8c:	e3a03003 	mov	r3, #3
47f33c90:	e59f002c 	ldr	r0, [pc, #44]	@ 0x47f33cc4
47f33c94:	e88d000c 	stm	sp, {r2, r3}
47f33c98:	eaffffe1 	b	0x47f33c24
47f33c9c:	e59f0024 	ldr	r0, [pc, #36]	@ 0x47f33cc8
47f33ca0:	e28dd008 	add	sp, sp, #8
47f33ca4:	e8bd4010 	pop	{r4, lr}
47f33ca8:	eaff5a2a 	b	0x47f0a558
47f33cac:	47f447e9 	ldrbmi	r4, [r4, r9, ror #15]!
47f33cb0:	92040000 	andls	r0, r4, #0
47f33cb4:	27912810 			@ <UNDEFINED> instruction: 0x27912810
47f33cb8:	94000050 	strls	r0, [r0], #-80	@ 0xffffffb0
47f33cbc:	004fdf3b 	subeq	sp, pc, r11, lsr pc	@ <UNPREDICTABLE>
47f33cc0:	27912710 			@ <UNDEFINED> instruction: 0x27912710
47f33cc4:	94000058 	strls	r0, [r0], #-88	@ 0xffffffa8
47f33cc8:	47f4480a 	ldrbmi	r4, [r4, r10, lsl #16]!
47f33ccc:	e59f312c 	ldr	r3, [pc, #300]	@ 0x47f33e00
47f33cd0:	e5931000 	ldr	r1, [r3]
47f33cd4:	e59f2128 	ldr	r2, [pc, #296]	@ 0x47f33e04
47f33cd8:	e1510002 	cmp	r1, r2
47f33cdc:	1a000014 	bne	0x47f33d34
47f33ce0:	e59f3120 	ldr	r3, [pc, #288]	@ 0x47f33e08
47f33ce4:	e59f2120 	ldr	r2, [pc, #288]	@ 0x47f33e0c
47f33ce8:	e59f1120 	ldr	r1, [pc, #288]	@ 0x47f33e10
47f33cec:	e5832000 	str	r2, [r3]
47f33cf0:	e3a0208f 	mov	r2, #143	@ 0x8f
47f33cf4:	e5832004 	str	r2, [r3, #4]
47f33cf8:	e3a02d15 	mov	r2, #1344	@ 0x540
47f33cfc:	e5832008 	str	r2, [r3, #8]
47f33d00:	e3a02004 	mov	r2, #4
47f33d04:	e583200c 	str	r2, [r3, #12]
47f33d08:	e3a02000 	mov	r2, #0
47f33d0c:	e5832010 	str	r2, [r3, #16]
47f33d10:	e5831014 	str	r1, [r3, #20]
47f33d14:	e59f10f8 	ldr	r1, [pc, #248]	@ 0x47f33e14
47f33d18:	e5831018 	str	r1, [r3, #24]
47f33d1c:	e59f10f4 	ldr	r1, [pc, #244]	@ 0x47f33e18
47f33d20:	e583101c 	str	r1, [r3, #28]
47f33d24:	e3a01101 	mov	r1, #1073741824	@ 0x40000000
47f33d28:	e5831020 	str	r1, [r3, #32]
47f33d2c:	e59f10e8 	ldr	r1, [pc, #232]	@ 0x47f33e1c
47f33d30:	ea000017 	b	0x47f33d94
47f33d34:	e5932000 	ldr	r2, [r3]
47f33d38:	e59f30e0 	ldr	r3, [pc, #224]	@ 0x47f33e20
47f33d3c:	e1520003 	cmp	r2, r3
47f33d40:	112fff1e 	bxne	lr
47f33d44:	e59f30bc 	ldr	r3, [pc, #188]	@ 0x47f33e08
47f33d48:	e59f20bc 	ldr	r2, [pc, #188]	@ 0x47f33e0c
47f33d4c:	e59f10bc 	ldr	r1, [pc, #188]	@ 0x47f33e10
47f33d50:	e5832000 	str	r2, [r3]
47f33d54:	e3a0208f 	mov	r2, #143	@ 0x8f
47f33d58:	e5832004 	str	r2, [r3, #4]
47f33d5c:	e3a02d15 	mov	r2, #1344	@ 0x540
47f33d60:	e5832008 	str	r2, [r3, #8]
47f33d64:	e3a02004 	mov	r2, #4
47f33d68:	e583200c 	str	r2, [r3, #12]
47f33d6c:	e3a02000 	mov	r2, #0
47f33d70:	e5832010 	str	r2, [r3, #16]
47f33d74:	e5831014 	str	r1, [r3, #20]
47f33d78:	e59f1094 	ldr	r1, [pc, #148]	@ 0x47f33e14
47f33d7c:	e5831018 	str	r1, [r3, #24]
47f33d80:	e59f1090 	ldr	r1, [pc, #144]	@ 0x47f33e18
47f33d84:	e583101c 	str	r1, [r3, #28]
47f33d88:	e3a01311 	mov	r1, #1140850688	@ 0x44000000
47f33d8c:	e5831020 	str	r1, [r3, #32]
47f33d90:	e59f108c 	ldr	r1, [pc, #140]	@ 0x47f33e24
47f33d94:	e5831024 	str	r1, [r3, #36]	@ 0x24
47f33d98:	e59f1088 	ldr	r1, [pc, #136]	@ 0x47f33e28
47f33d9c:	e5832028 	str	r2, [r3, #40]	@ 0x28
47f33da0:	e583202c 	str	r2, [r3, #44]	@ 0x2c
47f33da4:	e5831030 	str	r1, [r3, #48]	@ 0x30
47f33da8:	e59f107c 	ldr	r1, [pc, #124]	@ 0x47f33e2c
47f33dac:	e5831034 	str	r1, [r3, #52]	@ 0x34
47f33db0:	e3001f0f 	movw	r1, #3855	@ 0xf0f
47f33db4:	e5831038 	str	r1, [r3, #56]	@ 0x38
47f33db8:	e583203c 	str	r2, [r3, #60]	@ 0x3c
47f33dbc:	e3a0270f 	mov	r2, #3932160	@ 0x3c0000
47f33dc0:	e5832040 	str	r2, [r3, #64]	@ 0x40
47f33dc4:	e59f2064 	ldr	r2, [pc, #100]	@ 0x47f33e30
47f33dc8:	e5832044 	str	r2, [r3, #68]	@ 0x44
47f33dcc:	e59f2060 	ldr	r2, [pc, #96]	@ 0x47f33e34
47f33dd0:	e5832048 	str	r2, [r3, #72]	@ 0x48
47f33dd4:	e59f205c 	ldr	r2, [pc, #92]	@ 0x47f33e38
47f33dd8:	e583204c 	str	r2, [r3, #76]	@ 0x4c
47f33ddc:	e59f2058 	ldr	r2, [pc, #88]	@ 0x47f33e3c
47f33de0:	e5832050 	str	r2, [r3, #80]	@ 0x50
47f33de4:	e5832054 	str	r2, [r3, #84]	@ 0x54
47f33de8:	e282220d 	add	r2, r2, #-805306368	@ 0xd0000000
47f33dec:	e28228af 	add	r2, r2, #11468800	@ 0xaf0000
47f33df0:	e5832058 	str	r2, [r3, #88]	@ 0x58
47f33df4:	e59f2044 	ldr	r2, [pc, #68]	@ 0x47f33e40
47f33df8:	e583205c 	str	r2, [r3, #92]	@ 0x5c
47f33dfc:	e12fff1e 	bx	lr
47f33e00:	92040000 	andls	r0, r4, #0
47f33e04:	27912810 			@ <UNDEFINED> instruction: 0x27912810
47f33e08:	9fe00000 	svcls	0x00e00000
47f33e0c:	800180a7 	andhi	r8, r1, r7, lsr #1
47f33e10:	018a6400 	orreq	r6, r10, r0, lsl #8
47f33e14:	00b50140 	adcseq	r0, r5, r0, asr #2
47f33e18:	01216000 			@ <UNDEFINED> instruction: 0x01216000
47f33e1c:	0b510007 	bleq	0x49373e40
47f33e20:	27912710 			@ <UNDEFINED> instruction: 0x27912710
47f33e24:	0b510027 	bleq	0x49373ec8
47f33e28:	a02e2400 	eorge	r2, lr, r0, lsl #8
47f33e2c:	c0593d44 	subsgt	r3, r9, r4, asr #26
47f33e30:	ea00a013 	b	0x47f5be84
47f33e34:	101038ca 	andsne	r3, r0, r10, asr #17
47f33e38:	0005a008 	andeq	r10, r5, r8
47f33e3c:	33333333 	teqcc	r3, #-872415232	@ 0xcc000000
47f33e40:	00040244 	andeq	r0, r4, r4, asr #4
47f33e44:	e3500001 	cmp	r0, #1
47f33e48:	e92d4008 	push	{r3, lr}
47f33e4c:	0a00001a 	beq	0x47f33ebc
47f33e50:	3a000034 	bcc	0x47f33f28
47f33e54:	e3500003 	cmp	r0, #3
47f33e58:	18bd8008 	popne	{r3, pc}
47f33e5c:	e59f30d0 	ldr	r3, [pc, #208]	@ 0x47f33f34
47f33e60:	e5932000 	ldr	r2, [r3]
47f33e64:	e3c220ff 	bic	r2, r2, #255	@ 0xff
47f33e68:	e38220a5 	orr	r2, r2, #165	@ 0xa5
47f33e6c:	e5832000 	str	r2, [r3]
47f33e70:	e5932008 	ldr	r2, [r3, #8]
47f33e74:	e3c220ff 	bic	r2, r2, #255	@ 0xff
47f33e78:	e3822020 	orr	r2, r2, #32
47f33e7c:	e5832008 	str	r2, [r3, #8]
47f33e80:	e593200c 	ldr	r2, [r3, #12]
47f33e84:	e3c220ff 	bic	r2, r2, #255	@ 0xff
47f33e88:	e3822005 	orr	r2, r2, #5
47f33e8c:	e583200c 	str	r2, [r3, #12]
47f33e90:	e5932014 	ldr	r2, [r3, #20]
47f33e94:	e3c22cff 	bic	r2, r2, #65280	@ 0xff00
47f33e98:	e3822b16 	orr	r2, r2, #22528	@ 0x5800
47f33e9c:	e5832014 	str	r2, [r3, #20]
47f33ea0:	e5932020 	ldr	r2, [r3, #32]
47f33ea4:	e3c224ff 	bic	r2, r2, #-16777216	@ 0xff000000
47f33ea8:	e5832020 	str	r2, [r3, #32]
47f33eac:	e5932024 	ldr	r2, [r3, #36]	@ 0x24
47f33eb0:	e3c220ff 	bic	r2, r2, #255	@ 0xff
47f33eb4:	e3822083 	orr	r2, r2, #131	@ 0x83
47f33eb8:	ea000018 	b	0x47f33f20
47f33ebc:	e59f0074 	ldr	r0, [pc, #116]	@ 0x47f33f38
47f33ec0:	ebff59a4 	bl	0x47f0a558
47f33ec4:	e59f3068 	ldr	r3, [pc, #104]	@ 0x47f33f34
47f33ec8:	e5932000 	ldr	r2, [r3]
47f33ecc:	e3c220ff 	bic	r2, r2, #255	@ 0xff
47f33ed0:	e38220a5 	orr	r2, r2, #165	@ 0xa5
47f33ed4:	e5832000 	str	r2, [r3]
47f33ed8:	e5932008 	ldr	r2, [r3, #8]
47f33edc:	e3c220ff 	bic	r2, r2, #255	@ 0xff
47f33ee0:	e3822020 	orr	r2, r2, #32
47f33ee4:	e5832008 	str	r2, [r3, #8]
47f33ee8:	e5932014 	ldr	r2, [r3, #20]
47f33eec:	e3c22cff 	bic	r2, r2, #65280	@ 0xff00
47f33ef0:	e3822b16 	orr	r2, r2, #22528	@ 0x5800
47f33ef4:	e5832014 	str	r2, [r3, #20]
47f33ef8:	e5932020 	ldr	r2, [r3, #32]
47f33efc:	e3c224ff 	bic	r2, r2, #-16777216	@ 0xff000000
47f33f00:	e5832020 	str	r2, [r3, #32]
47f33f04:	e5932024 	ldr	r2, [r3, #36]	@ 0x24
47f33f08:	e3c220ff 	bic	r2, r2, #255	@ 0xff
47f33f0c:	e3822003 	orr	r2, r2, #3
47f33f10:	e5832024 	str	r2, [r3, #36]	@ 0x24
47f33f14:	e5932024 	ldr	r2, [r3, #36]	@ 0x24
47f33f18:	e3c228ff 	bic	r2, r2, #16711680	@ 0xff0000
47f33f1c:	e3822857 	orr	r2, r2, #5701632	@ 0x570000
47f33f20:	e5832024 	str	r2, [r3, #36]	@ 0x24
47f33f24:	e8bd8008 	pop	{r3, pc}
47f33f28:	e59f000c 	ldr	r0, [pc, #12]	@ 0x47f33f3c
47f33f2c:	e8bd4008 	pop	{r3, lr}
47f33f30:	eaff5988 	b	0x47f0a558
47f33f34:	9fe00000 	svcls	0x00e00000
47f33f38:	47f44820 	ldrbmi	r4, [r4, r0, lsr #16]!
47f33f3c:	47f44833 			@ <UNDEFINED> instruction: 0x47f44833
47f33f40:	e59f313c 	ldr	r3, [pc, #316]	@ 0x47f34084
47f33f44:	e92d4010 	push	{r4, lr}
47f33f48:	e5931000 	ldr	r1, [r3]
47f33f4c:	e59f2134 	ldr	r2, [pc, #308]	@ 0x47f34088
47f33f50:	e1510002 	cmp	r1, r2
47f33f54:	1a00001d 	bne	0x47f33fd0
47f33f58:	e3a04325 	mov	r4, #-1811939328	@ 0x94000000
47f33f5c:	e3a00000 	mov	r0, #0
47f33f60:	ebffff17 	bl	0x47f33bc4
47f33f64:	e5943008 	ldr	r3, [r4, #8]
47f33f68:	e3a00064 	mov	r0, #100	@ 0x64
47f33f6c:	e3c33020 	bic	r3, r3, #32
47f33f70:	e5843008 	str	r3, [r4, #8]
47f33f74:	e5943008 	ldr	r3, [r4, #8]
47f33f78:	e3c33010 	bic	r3, r3, #16
47f33f7c:	e5843008 	str	r3, [r4, #8]
47f33f80:	ebffca5b 	bl	0x47f268f4
47f33f84:	e5943008 	ldr	r3, [r4, #8]
47f33f88:	e3a00064 	mov	r0, #100	@ 0x64
47f33f8c:	e3833020 	orr	r3, r3, #32
47f33f90:	e5843008 	str	r3, [r4, #8]
47f33f94:	ebffca56 	bl	0x47f268f4
47f33f98:	ebffff4b 	bl	0x47f33ccc
47f33f9c:	e59f00e8 	ldr	r0, [pc, #232]	@ 0x47f3408c
47f33fa0:	ebff596c 	bl	0x47f0a558
47f33fa4:	e59f20e4 	ldr	r2, [pc, #228]	@ 0x47f34090
47f33fa8:	e5943008 	ldr	r3, [r4, #8]
47f33fac:	e3833010 	orr	r3, r3, #16
47f33fb0:	e5843008 	str	r3, [r4, #8]
47f33fb4:	e5923010 	ldr	r3, [r2, #16]
47f33fb8:	e3c33b02 	bic	r3, r3, #2048	@ 0x800
47f33fbc:	e5823010 	str	r3, [r2, #16]
47f33fc0:	e594300c 	ldr	r3, [r4, #12]
47f33fc4:	e3833e1e 	orr	r3, r3, #480	@ 0x1e0
47f33fc8:	e584300c 	str	r3, [r4, #12]
47f33fcc:	ea00002a 	b	0x47f3407c
47f33fd0:	e5932000 	ldr	r2, [r3]
47f33fd4:	e59f30b8 	ldr	r3, [pc, #184]	@ 0x47f34094
47f33fd8:	e1520003 	cmp	r2, r3
47f33fdc:	1a000026 	bne	0x47f3407c
47f33fe0:	e3a04325 	mov	r4, #-1811939328	@ 0x94000000
47f33fe4:	e3a00000 	mov	r0, #0
47f33fe8:	ebfffef5 	bl	0x47f33bc4
47f33fec:	e594302c 	ldr	r3, [r4, #44]	@ 0x2c
47f33ff0:	e3a00064 	mov	r0, #100	@ 0x64
47f33ff4:	e3c33002 	bic	r3, r3, #2
47f33ff8:	e584302c 	str	r3, [r4, #44]	@ 0x2c
47f33ffc:	e594302c 	ldr	r3, [r4, #44]	@ 0x2c
47f34000:	e3c33001 	bic	r3, r3, #1
47f34004:	e584302c 	str	r3, [r4, #44]	@ 0x2c
47f34008:	ebffca39 	bl	0x47f268f4
47f3400c:	e594302c 	ldr	r3, [r4, #44]	@ 0x2c
47f34010:	e3a00064 	mov	r0, #100	@ 0x64
47f34014:	e3833002 	orr	r3, r3, #2
47f34018:	e584302c 	str	r3, [r4, #44]	@ 0x2c
47f3401c:	ebffca34 	bl	0x47f268f4
47f34020:	ebffff29 	bl	0x47f33ccc
47f34024:	e59f0060 	ldr	r0, [pc, #96]	@ 0x47f3408c
47f34028:	ebff594a 	bl	0x47f0a558
47f3402c:	e59f205c 	ldr	r2, [pc, #92]	@ 0x47f34090
47f34030:	e594302c 	ldr	r3, [r4, #44]	@ 0x2c
47f34034:	e3833001 	orr	r3, r3, #1
47f34038:	e584302c 	str	r3, [r4, #44]	@ 0x2c
47f3403c:	e5923010 	ldr	r3, [r2, #16]
47f34040:	e3c33b02 	bic	r3, r3, #2048	@ 0x800
47f34044:	e5823010 	str	r3, [r2, #16]
47f34048:	e59f3048 	ldr	r3, [pc, #72]	@ 0x47f34098
47f3404c:	e5931008 	ldr	r1, [r3, #8]
47f34050:	e5923010 	ldr	r3, [r2, #16]
47f34054:	e7e31c51 	ubfx	r1, r1, #24, #4
47f34058:	e3c33d0f 	bic	r3, r3, #960	@ 0x3c0
47f3405c:	e1833301 	orr	r3, r3, r1, lsl #6
47f34060:	e5823010 	str	r3, [r2, #16]
47f34064:	e5943010 	ldr	r3, [r4, #16]
47f34068:	e3833070 	orr	r3, r3, #112	@ 0x70
47f3406c:	e5843010 	str	r3, [r4, #16]
47f34070:	e5943010 	ldr	r3, [r4, #16]
47f34074:	e3833003 	orr	r3, r3, #3
47f34078:	e5843010 	str	r3, [r4, #16]
47f3407c:	e3a00000 	mov	r0, #0
47f34080:	e8bd8010 	pop	{r4, pc}
47f34084:	92040000 	andls	r0, r4, #0
47f34088:	27912810 			@ <UNDEFINED> instruction: 0x27912810
47f3408c:	47f44833 			@ <UNDEFINED> instruction: 0x47f44833
47f34090:	94100000 	ldrls	r0, [r0], #-0
47f34094:	27912710 			@ <UNDEFINED> instruction: 0x27912710
47f34098:	9a107000 	bls	0x483500a0
47f3409c:	e92d4038 	push	{r3, r4, r5, lr}
47f340a0:	e3500000 	cmp	r0, #0
47f340a4:	e59f40dc 	ldr	r4, [pc, #220]	@ 0x47f34188
47f340a8:	e594302c 	ldr	r3, [r4, #44]	@ 0x2c
47f340ac:	1a000018 	bne	0x47f34114
47f340b0:	e38330d5 	orr	r3, r3, #213	@ 0xd5
47f340b4:	e3a00032 	mov	r0, #50	@ 0x32
47f340b8:	e584302c 	str	r3, [r4, #44]	@ 0x2c
47f340bc:	e3a05325 	mov	r5, #-1811939328	@ 0x94000000
47f340c0:	ebffca17 	bl	0x47f26924
47f340c4:	e5953008 	ldr	r3, [r5, #8]
47f340c8:	e3833a02 	orr	r3, r3, #8192	@ 0x2000
47f340cc:	e3a00032 	mov	r0, #50	@ 0x32
47f340d0:	e5853008 	str	r3, [r5, #8]
47f340d4:	ebffca12 	bl	0x47f26924
47f340d8:	e5953008 	ldr	r3, [r5, #8]
47f340dc:	e3833903 	orr	r3, r3, #49152	@ 0xc000
47f340e0:	e3a00032 	mov	r0, #50	@ 0x32
47f340e4:	e5853008 	str	r3, [r5, #8]
47f340e8:	ebffca0d 	bl	0x47f26924
47f340ec:	e5953024 	ldr	r3, [r5, #36]	@ 0x24
47f340f0:	e3c33301 	bic	r3, r3, #67108864	@ 0x4000000
47f340f4:	e3a00032 	mov	r0, #50	@ 0x32
47f340f8:	e5853024 	str	r3, [r5, #36]	@ 0x24
47f340fc:	ebffca08 	bl	0x47f26924
47f34100:	e594302c 	ldr	r3, [r4, #44]	@ 0x2c
47f34104:	e3c33c01 	bic	r3, r3, #256	@ 0x100
47f34108:	e3a02695 	mov	r2, #156237824	@ 0x9500000
47f3410c:	e584302c 	str	r3, [r4, #44]	@ 0x2c
47f34110:	ea000018 	b	0x47f34178
47f34114:	e3833b6a 	orr	r3, r3, #108544	@ 0x1a800
47f34118:	e3833c02 	orr	r3, r3, #512	@ 0x200
47f3411c:	e3a00032 	mov	r0, #50	@ 0x32
47f34120:	e584302c 	str	r3, [r4, #44]	@ 0x2c
47f34124:	e3a05325 	mov	r5, #-1811939328	@ 0x94000000
47f34128:	ebffc9fd 	bl	0x47f26924
47f3412c:	e5953008 	ldr	r3, [r5, #8]
47f34130:	e3833402 	orr	r3, r3, #33554432	@ 0x2000000
47f34134:	e3a00032 	mov	r0, #50	@ 0x32
47f34138:	e5853008 	str	r3, [r5, #8]
47f3413c:	ebffc9f8 	bl	0x47f26924
47f34140:	e5953008 	ldr	r3, [r5, #8]
47f34144:	e3833303 	orr	r3, r3, #201326592	@ 0xc000000
47f34148:	e3a00032 	mov	r0, #50	@ 0x32
47f3414c:	e5853008 	str	r3, [r5, #8]
47f34150:	ebffc9f3 	bl	0x47f26924
47f34154:	e5953024 	ldr	r3, [r5, #36]	@ 0x24
47f34158:	e3c33301 	bic	r3, r3, #67108864	@ 0x4000000
47f3415c:	e3a00032 	mov	r0, #50	@ 0x32
47f34160:	e5853024 	str	r3, [r5, #36]	@ 0x24
47f34164:	ebffc9ee 	bl	0x47f26924
47f34168:	e594302c 	ldr	r3, [r4, #44]	@ 0x2c
47f3416c:	e3c33802 	bic	r3, r3, #131072	@ 0x20000
47f34170:	e3a02696 	mov	r2, #157286400	@ 0x9600000
47f34174:	e584302c 	str	r3, [r4, #44]	@ 0x2c
47f34178:	e5923000 	ldr	r3, [r2]
47f3417c:	e3833020 	orr	r3, r3, #32
47f34180:	e5823000 	str	r3, [r2]
47f34184:	e8bd8038 	pop	{r3, r4, r5, pc}
47f34188:	94100000 	ldrls	r0, [r0], #-0
47f3418c:	e92d4010 	push	{r4, lr}
47f34190:	e1a04000 	mov	r4, r0
47f34194:	e3a00032 	mov	r0, #50	@ 0x32
47f34198:	ebffc9e1 	bl	0x47f26924
47f3419c:	e59f3014 	ldr	r3, [pc, #20]	@ 0x47f341b8
47f341a0:	e3540000 	cmp	r4, #0
47f341a4:	e5932054 	ldr	r2, [r3, #84]	@ 0x54
47f341a8:	03822001 	orreq	r2, r2, #1
47f341ac:	13822008 	orrne	r2, r2, #8
47f341b0:	e5832054 	str	r2, [r3, #84]	@ 0x54
47f341b4:	e8bd8010 	pop	{r4, pc}
47f341b8:	94100000 	ldrls	r0, [r0], #-0
47f341bc:	e1a03001 	mov	r3, r1
47f341c0:	e16f1f11 	clz	r1, r1
47f341c4:	e1a012a1 	lsr	r1, r1, #5
47f341c8:	e3500003 	cmp	r0, #3
47f341cc:	83811001 	orrhi	r1, r1, #1
47f341d0:	e3510000 	cmp	r1, #0
47f341d4:	1a000014 	bne	0x47f3422c
47f341d8:	e52de004 	push	{lr}		@ (str lr, [sp, #-4]!)
47f341dc:	e5d32003 	ldrb	r2, [r3, #3]
47f341e0:	e5d3c002 	ldrb	r12, [r3, #2]
47f341e4:	e59fe048 	ldr	lr, [pc, #72]	@ 0x47f34234
47f341e8:	e1a02802 	lsl	r2, r2, #16
47f341ec:	e1822c0c 	orr	r2, r2, r12, lsl #24
47f341f0:	e5d3c005 	ldrb	r12, [r3, #5]
47f341f4:	e182200c 	orr	r2, r2, r12
47f341f8:	e5d3c004 	ldrb	r12, [r3, #4]
47f341fc:	e182240c 	orr	r2, r2, r12, lsl #8
47f34200:	e3a0c008 	mov	r12, #8
47f34204:	e10ee08c 	smlabb	lr, r12, r0, lr
47f34208:	e58e2000 	str	r2, [lr]
47f3420c:	e5d32000 	ldrb	r2, [r3]
47f34210:	e5d33001 	ldrb	r3, [r3, #1]
47f34214:	e1833c12 	orr	r3, r3, r2, lsl r12
47f34218:	e59f2018 	ldr	r2, [pc, #24]	@ 0x47f34238
47f3421c:	e10c208c 	smlabb	r12, r12, r0, r2
47f34220:	e1a00001 	mov	r0, r1
47f34224:	e58c3000 	str	r3, [r12]
47f34228:	e49df004 	pop	{pc}		@ (ldr pc, [sp], #4)
47f3422c:	e3e00000 	mvn	r0, #0
47f34230:	e12fff1e 	bx	lr
47f34234:	923a0078 	eorsls	r0, r10, #120	@ 0x78
47f34238:	923a007c 	eorsls	r0, r10, #124	@ 0x7c
47f3423c:	e92d4008 	push	{r3, lr}
47f34240:	eb000201 	bl	0x47f34a4c
47f34244:	eb00053c 	bl	0x47f3573c
47f34248:	eb000650 	bl	0x47f35b90
47f3424c:	e59f300c 	ldr	r3, [pc, #12]	@ 0x47f34260
47f34250:	e3a02011 	mov	r2, #17
47f34254:	e3a00000 	mov	r0, #0
47f34258:	e58320e0 	str	r2, [r3, #224]	@ 0xe0
47f3425c:	e8bd8008 	pop	{r3, pc}
47f34260:	923a0000 	eorsls	r0, r10, #0
47f34264:	e92d4010 	push	{r4, lr}
47f34268:	e3a04492 	mov	r4, #-1845493760	@ 0x92000000
47f3426c:	e5943008 	ldr	r3, [r4, #8]
47f34270:	e1c30000 	bic	r0, r3, r0
47f34274:	e5840008 	str	r0, [r4, #8]
47f34278:	e3a0000a 	mov	r0, #10
47f3427c:	ebffc9a8 	bl	0x47f26924
47f34280:	e3e03000 	mvn	r3, #0
47f34284:	e5843008 	str	r3, [r4, #8]
47f34288:	e8bd8010 	pop	{r4, pc}
47f3428c:	e59f3004 	ldr	r3, [pc, #4]	@ 0x47f34298
47f34290:	e5930000 	ldr	r0, [r3]
47f34294:	e12fff1e 	bx	lr
47f34298:	47f62304 	ldrbmi	r2, [r6, r4, lsl #6]!
47f3429c:	e92d4038 	push	{r3, r4, r5, lr}
47f342a0:	e59f403c 	ldr	r4, [pc, #60]	@ 0x47f342e4
47f342a4:	e5945000 	ldr	r5, [r4]
47f342a8:	e3550000 	cmp	r5, #0
47f342ac:	1a00000a 	bne	0x47f342dc
47f342b0:	e3e00000 	mvn	r0, #0
47f342b4:	ebffffea 	bl	0x47f34264
47f342b8:	ebffffdf 	bl	0x47f3423c
47f342bc:	e59f3024 	ldr	r3, [pc, #36]	@ 0x47f342e8
47f342c0:	e3a0200f 	mov	r2, #15
47f342c4:	e3a00014 	mov	r0, #20
47f342c8:	e5835018 	str	r5, [r3, #24]
47f342cc:	e583201c 	str	r2, [r3, #28]
47f342d0:	ebffc993 	bl	0x47f26924
47f342d4:	e3a03001 	mov	r3, #1
47f342d8:	e5843000 	str	r3, [r4]
47f342dc:	e3a00000 	mov	r0, #0
47f342e0:	e8bd8038 	pop	{r3, r4, r5, pc}
47f342e4:	47f62304 	ldrbmi	r2, [r6, r4, lsl #6]!
47f342e8:	92040000 	andls	r0, r4, #0
47f342ec:	e59f32ac 	ldr	r3, [pc, #684]	@ 0x47f345a0
47f342f0:	e3a02000 	mov	r2, #0
47f342f4:	e59f02a8 	ldr	r0, [pc, #680]	@ 0x47f345a4
47f342f8:	e59f12a8 	ldr	r1, [pc, #680]	@ 0x47f345a8
47f342fc:	e92d4010 	push	{r4, lr}
47f34300:	e5832000 	str	r2, [r3]
47f34304:	e5830004 	str	r0, [r3, #4]
47f34308:	e5830008 	str	r0, [r3, #8]
47f3430c:	e591c000 	ldr	r12, [r1]
47f34310:	e59f2294 	ldr	r2, [pc, #660]	@ 0x47f345ac
47f34314:	e15c0002 	cmp	r12, r2
47f34318:	05830018 	streq	r0, [r3, #24]
47f3431c:	0583001c 	streq	r0, [r3, #28]
47f34320:	e5913000 	ldr	r3, [r1]
47f34324:	e59f0284 	ldr	r0, [pc, #644]	@ 0x47f345b0
47f34328:	e1530000 	cmp	r3, r0
47f3432c:	e59f326c 	ldr	r3, [pc, #620]	@ 0x47f345a0
47f34330:	03a0103f 	moveq	r1, #63	@ 0x3f
47f34334:	0a000004 	beq	0x47f3434c
47f34338:	e59f1268 	ldr	r1, [pc, #616]	@ 0x47f345a8
47f3433c:	e5911000 	ldr	r1, [r1]
47f34340:	e1510002 	cmp	r1, r2
47f34344:	1a000001 	bne	0x47f34350
47f34348:	e30011ff 	movw	r1, #511	@ 0x1ff
47f3434c:	e5831058 	str	r1, [r3, #88]	@ 0x58
47f34350:	e3a0100f 	mov	r1, #15
47f34354:	e583105c 	str	r1, [r3, #92]	@ 0x5c
47f34358:	e59f3248 	ldr	r3, [pc, #584]	@ 0x47f345a8
47f3435c:	e5931000 	ldr	r1, [r3]
47f34360:	e1510000 	cmp	r1, r0
47f34364:	1a000017 	bne	0x47f343c8
47f34368:	e59f3244 	ldr	r3, [pc, #580]	@ 0x47f345b4
47f3436c:	e59f1244 	ldr	r1, [pc, #580]	@ 0x47f345b8
47f34370:	e59fc244 	ldr	r12, [pc, #580]	@ 0x47f345bc
47f34374:	e5831000 	str	r1, [r3]
47f34378:	e5831004 	str	r1, [r3, #4]
47f3437c:	e2811902 	add	r1, r1, #32768	@ 0x8000
47f34380:	e5831008 	str	r1, [r3, #8]
47f34384:	e583100c 	str	r1, [r3, #12]
47f34388:	e3a01000 	mov	r1, #0
47f3438c:	e6bfefb1 	rev16	lr, r1
47f34390:	e2811001 	add	r1, r1, #1
47f34394:	e3510b02 	cmp	r1, #2048	@ 0x800
47f34398:	e1ece0b2 	strh	lr, [r12, #2]!
47f3439c:	1afffffa 	bne	0x47f3438c
47f343a0:	e59fc218 	ldr	r12, [pc, #536]	@ 0x47f345c0
47f343a4:	e3a01000 	mov	r1, #0
47f343a8:	e6bfefb1 	rev16	lr, r1
47f343ac:	e2811001 	add	r1, r1, #1
47f343b0:	e3510c02 	cmp	r1, #512	@ 0x200
47f343b4:	e1ece0b2 	strh	lr, [r12, #2]!
47f343b8:	1afffffa 	bne	0x47f343a8
47f343bc:	e3a01000 	mov	r1, #0
47f343c0:	e5831010 	str	r1, [r3, #16]
47f343c4:	ea00002d 	b	0x47f34480
47f343c8:	e5933000 	ldr	r3, [r3]
47f343cc:	e1530002 	cmp	r3, r2
47f343d0:	1a00002a 	bne	0x47f34480
47f343d4:	e59f31d8 	ldr	r3, [pc, #472]	@ 0x47f345b4
47f343d8:	e3a0e000 	mov	lr, #0
47f343dc:	e59f11d4 	ldr	r1, [pc, #468]	@ 0x47f345b8
47f343e0:	e59f41d4 	ldr	r4, [pc, #468]	@ 0x47f345bc
47f343e4:	e5831014 	str	r1, [r3, #20]
47f343e8:	e5831018 	str	r1, [r3, #24]
47f343ec:	e2811902 	add	r1, r1, #32768	@ 0x8000
47f343f0:	e583101c 	str	r1, [r3, #28]
47f343f4:	e1a0c001 	mov	r12, r1
47f343f8:	e5831020 	str	r1, [r3, #32]
47f343fc:	e6bf1fbe 	rev16	r1, lr
47f34400:	e28ee001 	add	lr, lr, #1
47f34404:	e35e0901 	cmp	lr, #16384	@ 0x4000
47f34408:	e1e410b2 	strh	r1, [r4, #2]!
47f3440c:	1afffffa 	bne	0x47f343fc
47f34410:	e59fe1a8 	ldr	lr, [pc, #424]	@ 0x47f345c0
47f34414:	e3a01000 	mov	r1, #0
47f34418:	e6bf4fb1 	rev16	r4, r1
47f3441c:	e2811001 	add	r1, r1, #1
47f34420:	e3510c02 	cmp	r1, #512	@ 0x200
47f34424:	e1ee40b2 	strh	r4, [lr, #2]!
47f34428:	1afffffa 	bne	0x47f34418
47f3442c:	e59fe184 	ldr	lr, [pc, #388]	@ 0x47f345b8
47f34430:	e3a01000 	mov	r1, #0
47f34434:	e583c02c 	str	r12, [r3, #44]	@ 0x2c
47f34438:	e583c030 	str	r12, [r3, #48]	@ 0x30
47f3443c:	e59fc178 	ldr	r12, [pc, #376]	@ 0x47f345bc
47f34440:	e5831010 	str	r1, [r3, #16]
47f34444:	e583e024 	str	lr, [r3, #36]	@ 0x24
47f34448:	e583e028 	str	lr, [r3, #40]	@ 0x28
47f3444c:	e1a03001 	mov	r3, r1
47f34450:	e6bf1fb3 	rev16	r1, r3
47f34454:	e2833001 	add	r3, r3, #1
47f34458:	e3530901 	cmp	r3, #16384	@ 0x4000
47f3445c:	e1ec10b2 	strh	r1, [r12, #2]!
47f34460:	1afffffa 	bne	0x47f34450
47f34464:	e59f1154 	ldr	r1, [pc, #340]	@ 0x47f345c0
47f34468:	e3a03000 	mov	r3, #0
47f3446c:	e6bfcfb3 	rev16	r12, r3
47f34470:	e2833001 	add	r3, r3, #1
47f34474:	e3530c02 	cmp	r3, #512	@ 0x200
47f34478:	e1e1c0b2 	strh	r12, [r1, #2]!
47f3447c:	1afffffa 	bne	0x47f3446c
47f34480:	e59f3120 	ldr	r3, [pc, #288]	@ 0x47f345a8
47f34484:	e5933000 	ldr	r3, [r3]
47f34488:	e1530002 	cmp	r3, r2
47f3448c:	1a000008 	bne	0x47f344b4
47f34490:	e59f312c 	ldr	r3, [pc, #300]	@ 0x47f345c4
47f34494:	e59f112c 	ldr	r1, [pc, #300]	@ 0x47f345c8
47f34498:	e58310f4 	str	r1, [r3, #244]	@ 0xf4
47f3449c:	e2811501 	add	r1, r1, #4194304	@ 0x400000
47f344a0:	e58310f8 	str	r1, [r3, #248]	@ 0xf8
47f344a4:	e3a01441 	mov	r1, #1090519040	@ 0x41000000
47f344a8:	e58310c8 	str	r1, [r3, #200]	@ 0xc8
47f344ac:	e2811501 	add	r1, r1, #4194304	@ 0x400000
47f344b0:	e58310cc 	str	r1, [r3, #204]	@ 0xcc
47f344b4:	e59f10ec 	ldr	r1, [pc, #236]	@ 0x47f345a8
47f344b8:	e5913000 	ldr	r3, [r1]
47f344bc:	e1530000 	cmp	r3, r0
47f344c0:	e59f30fc 	ldr	r3, [pc, #252]	@ 0x47f345c4
47f344c4:	1a000009 	bne	0x47f344f0
47f344c8:	e3a01441 	mov	r1, #1090519040	@ 0x41000000
47f344cc:	e58310f4 	str	r1, [r3, #244]	@ 0xf4
47f344d0:	e2811501 	add	r1, r1, #4194304	@ 0x400000
47f344d4:	e58310f8 	str	r1, [r3, #248]	@ 0xf8
47f344d8:	e59f10d4 	ldr	r1, [pc, #212]	@ 0x47f345b4
47f344dc:	e591c000 	ldr	r12, [r1]
47f344e0:	e583c0e8 	str	r12, [r3, #232]	@ 0xe8
47f344e4:	e5911008 	ldr	r1, [r1, #8]
47f344e8:	e58310ec 	str	r1, [r3, #236]	@ 0xec
47f344ec:	ea00000b 	b	0x47f34520
47f344f0:	e5911000 	ldr	r1, [r1]
47f344f4:	e1510002 	cmp	r1, r2
47f344f8:	1a000008 	bne	0x47f34520
47f344fc:	e59f10b0 	ldr	r1, [pc, #176]	@ 0x47f345b4
47f34500:	e591c014 	ldr	r12, [r1, #20]
47f34504:	e583c0e8 	str	r12, [r3, #232]	@ 0xe8
47f34508:	e591c01c 	ldr	r12, [r1, #28]
47f3450c:	e583c0ec 	str	r12, [r3, #236]	@ 0xec
47f34510:	e591c024 	ldr	r12, [r1, #36]	@ 0x24
47f34514:	e583c0c0 	str	r12, [r3, #192]	@ 0xc0
47f34518:	e591102c 	ldr	r1, [r1, #44]	@ 0x2c
47f3451c:	e58310c4 	str	r1, [r3, #196]	@ 0xc4
47f34520:	e59f109c 	ldr	r1, [pc, #156]	@ 0x47f345c4
47f34524:	e59fc0a0 	ldr	r12, [pc, #160]	@ 0x47f345cc
47f34528:	e59f3078 	ldr	r3, [pc, #120]	@ 0x47f345a8
47f3452c:	e581c0fc 	str	r12, [r1, #252]	@ 0xfc
47f34530:	e593e000 	ldr	lr, [r3]
47f34534:	e15e0002 	cmp	lr, r2
47f34538:	0581c0d0 	streq	r12, [r1, #208]	@ 0xd0
47f3453c:	e5933000 	ldr	r3, [r3]
47f34540:	e1530000 	cmp	r3, r0
47f34544:	e59f3054 	ldr	r3, [pc, #84]	@ 0x47f345a0
47f34548:	03a02302 	moveq	r2, #134217728	@ 0x8000000
47f3454c:	05832048 	streq	r2, [r3, #72]	@ 0x48
47f34550:	03a02402 	moveq	r2, #33554432	@ 0x2000000
47f34554:	0583204c 	streq	r2, [r3, #76]	@ 0x4c
47f34558:	0a000008 	beq	0x47f34580
47f3455c:	e59f1044 	ldr	r1, [pc, #68]	@ 0x47f345a8
47f34560:	e5911000 	ldr	r1, [r1]
47f34564:	e1510002 	cmp	r1, r2
47f34568:	03a02101 	moveq	r2, #1073741824	@ 0x40000000
47f3456c:	05832048 	streq	r2, [r3, #72]	@ 0x48
47f34570:	05832060 	streq	r2, [r3, #96]	@ 0x60
47f34574:	03a02402 	moveq	r2, #33554432	@ 0x2000000
47f34578:	0583204c 	streq	r2, [r3, #76]	@ 0x4c
47f3457c:	05832064 	streq	r2, [r3, #100]	@ 0x64
47f34580:	e3a04000 	mov	r4, #0
47f34584:	e3a02008 	mov	r2, #8
47f34588:	e5834014 	str	r4, [r3, #20]
47f3458c:	e1a01004 	mov	r1, r4
47f34590:	e59f0038 	ldr	r0, [pc, #56]	@ 0x47f345d0
47f34594:	ebffc832 	bl	0x47f26664
47f34598:	e1a00004 	mov	r0, r4
47f3459c:	e8bd8010 	pop	{r4, pc}
47f345a0:	92348000 	eorsls	r8, r4, #0
47f345a4:	0104c040 	tsteq	r4, r0, asr #32
47f345a8:	92040000 	andls	r0, r4, #0
47f345ac:	27912710 			@ <UNDEFINED> instruction: 0x27912710
47f345b0:	27912810 			@ <UNDEFINED> instruction: 0x27912810
47f345b4:	47f62308 	ldrbmi	r2, [r6, r8, lsl #6]!
47f345b8:	41800000 	orrmi	r0, r0, r0
47f345bc:	417ffffe 	ldrshmi	pc, [pc, #-254]	@ 0x47f344c6	@ <UNPREDICTABLE>
47f345c0:	41807ffe 	strdmi	r7, [r0, lr]
47f345c4:	92340000 	eorsls	r0, r4, #0
47f345c8:	41002000 	mrsmi	r2, (UNDEF: 0)
47f345cc:	08000800 	stmdaeq	r0, {r11}
47f345d0:	47f6233c 			@ <UNDEFINED> instruction: 0x47f6233c
47f345d4:	e59f3008 	ldr	r3, [pc, #8]	@ 0x47f345e4
47f345d8:	e3a02000 	mov	r2, #0
47f345dc:	e5832000 	str	r2, [r3]
47f345e0:	e12fff1e 	bx	lr
47f345e4:	92348000 	eorsls	r8, r4, #0
47f345e8:	e59f3008 	ldr	r3, [pc, #8]	@ 0x47f345f8
47f345ec:	e3a02001 	mov	r2, #1
47f345f0:	e5832000 	str	r2, [r3]
47f345f4:	e12fff1e 	bx	lr
47f345f8:	92348000 	eorsls	r8, r4, #0
47f345fc:	e59f3060 	ldr	r3, [pc, #96]	@ 0x47f34664
47f34600:	e5932014 	ldr	r2, [r3, #20]
47f34604:	e3520000 	cmp	r2, #0
47f34608:	03a02001 	moveq	r2, #1
47f3460c:	05832014 	streq	r2, [r3, #20]
47f34610:	03a02004 	moveq	r2, #4
47f34614:	1a00000c 	bne	0x47f3464c
47f34618:	e593c014 	ldr	r12, [r3, #20]
47f3461c:	e59f1040 	ldr	r1, [pc, #64]	@ 0x47f34664
47f34620:	e35c0000 	cmp	r12, #0
47f34624:	0a000002 	beq	0x47f34634
47f34628:	e2522001 	subs	r2, r2, #1
47f3462c:	1afffff9 	bne	0x47f34618
47f34630:	ea000005 	b	0x47f3464c
47f34634:	e591000c 	ldr	r0, [r1, #12]
47f34638:	e3500000 	cmp	r0, #0
47f3463c:	aa000002 	bge	0x47f3464c
47f34640:	e581c014 	str	r12, [r1, #20]
47f34644:	e6ff0070 	uxth	r0, r0
47f34648:	e12fff1e 	bx	lr
47f3464c:	e59f2014 	ldr	r2, [pc, #20]	@ 0x47f34668
47f34650:	e3e0000a 	mvn	r0, #10
47f34654:	e5923034 	ldr	r3, [r2, #52]	@ 0x34
47f34658:	e2833001 	add	r3, r3, #1
47f3465c:	e5823034 	str	r3, [r2, #52]	@ 0x34
47f34660:	e12fff1e 	bx	lr
47f34664:	92348000 	eorsls	r8, r4, #0
47f34668:	47f62308 	ldrbmi	r2, [r6, r8, lsl #6]!
47f3466c:	e52de004 	push	{lr}		@ (str lr, [sp, #-4]!)
47f34670:	e3a01004 	mov	r1, #4
47f34674:	e59fc050 	ldr	r12, [pc, #80]	@ 0x47f346cc
47f34678:	e59fe050 	ldr	lr, [pc, #80]	@ 0x47f346d0
47f3467c:	e59c3010 	ldr	r3, [r12, #16]
47f34680:	e59f2044 	ldr	r2, [pc, #68]	@ 0x47f346cc
47f34684:	e3530000 	cmp	r3, #0
47f34688:	0a000005 	beq	0x47f346a4
47f3468c:	e2433001 	sub	r3, r3, #1
47f34690:	e5823010 	str	r3, [r2, #16]
47f34694:	e59f3034 	ldr	r3, [pc, #52]	@ 0x47f346d0
47f34698:	e5830010 	str	r0, [r3, #16]
47f3469c:	e3a00000 	mov	r0, #0
47f346a0:	e49df004 	pop	{pc}		@ (ldr pc, [sp], #4)
47f346a4:	e59e30dc 	ldr	r3, [lr, #220]	@ 0xdc
47f346a8:	e2511001 	subs	r1, r1, #1
47f346ac:	e7e531d3 	ubfx	r3, r3, #3, #6
47f346b0:	e58c3010 	str	r3, [r12, #16]
47f346b4:	1afffff0 	bne	0x47f3467c
47f346b8:	e5923038 	ldr	r3, [r2, #56]	@ 0x38
47f346bc:	e3e0000a 	mvn	r0, #10
47f346c0:	e2833001 	add	r3, r3, #1
47f346c4:	e5823038 	str	r3, [r2, #56]	@ 0x38
47f346c8:	e49df004 	pop	{pc}		@ (ldr pc, [sp], #4)
47f346cc:	47f62308 	ldrbmi	r2, [r6, r8, lsl #6]!
47f346d0:	92348000 	eorsls	r8, r4, #0
47f346d4:	e92d4010 	push	{r4, lr}
47f346d8:	e3a0c014 	mov	r12, #20
47f346dc:	e59fe05c 	ldr	lr, [pc, #92]	@ 0x47f34740
47f346e0:	e59e4018 	ldr	r4, [lr, #24]
47f346e4:	e59f3054 	ldr	r3, [pc, #84]	@ 0x47f34740
47f346e8:	e3140001 	tst	r4, #1
47f346ec:	0a00000b 	beq	0x47f34720
47f346f0:	e1800b02 	orr	r0, r0, r2, lsl #22
47f346f4:	e5830014 	str	r0, [r3, #20]
47f346f8:	e591200c 	ldr	r2, [r1, #12]
47f346fc:	e3a00000 	mov	r0, #0
47f34700:	e5832028 	str	r2, [r3, #40]	@ 0x28
47f34704:	e5912008 	ldr	r2, [r1, #8]
47f34708:	e5832024 	str	r2, [r3, #36]	@ 0x24
47f3470c:	e5912004 	ldr	r2, [r1, #4]
47f34710:	e5832020 	str	r2, [r3, #32]
47f34714:	e5912000 	ldr	r2, [r1]
47f34718:	e583201c 	str	r2, [r3, #28]
47f3471c:	e8bd8010 	pop	{r4, pc}
47f34720:	e25cc001 	subs	r12, r12, #1
47f34724:	1affffed 	bne	0x47f346e0
47f34728:	e59f2014 	ldr	r2, [pc, #20]	@ 0x47f34744
47f3472c:	e3e0000a 	mvn	r0, #10
47f34730:	e5923008 	ldr	r3, [r2, #8]
47f34734:	e2833001 	add	r3, r3, #1
47f34738:	e5823008 	str	r3, [r2, #8]
47f3473c:	e8bd8010 	pop	{r4, pc}
47f34740:	92344000 	eorsls	r4, r4, #0
47f34744:	47f62348 	ldrbmi	r2, [r6, r8, asr #6]!
47f34748:	e3510000 	cmp	r1, #0
47f3474c:	0a000020 	beq	0x47f347d4
47f34750:	e59fc084 	ldr	r12, [pc, #132]	@ 0x47f347dc
47f34754:	e3800302 	orr	r0, r0, #134217728	@ 0x8000000
47f34758:	e3a02014 	mov	r2, #20
47f3475c:	e92d4010 	push	{r4, lr}
47f34760:	e59c3018 	ldr	r3, [r12, #24]
47f34764:	e3130001 	tst	r3, #1
47f34768:	158c0014 	strne	r0, [r12, #20]
47f3476c:	13a0e014 	movne	lr, #20
47f34770:	1a000009 	bne	0x47f3479c
47f34774:	e2522001 	subs	r2, r2, #1
47f34778:	1afffff8 	bne	0x47f34760
47f3477c:	e59f205c 	ldr	r2, [pc, #92]	@ 0x47f347e0
47f34780:	e3e0000a 	mvn	r0, #10
47f34784:	e592300c 	ldr	r3, [r2, #12]
47f34788:	e2833001 	add	r3, r3, #1
47f3478c:	e582300c 	str	r3, [r2, #12]
47f34790:	e8bd8010 	pop	{r4, pc}
47f34794:	e25ee001 	subs	lr, lr, #1
47f34798:	0afffff5 	beq	0x47f34774
47f3479c:	e59c4018 	ldr	r4, [r12, #24]
47f347a0:	e59f3034 	ldr	r3, [pc, #52]	@ 0x47f347dc
47f347a4:	e3140001 	tst	r4, #1
47f347a8:	0afffff9 	beq	0x47f34794
47f347ac:	e5932028 	ldr	r2, [r3, #40]	@ 0x28
47f347b0:	e3a00000 	mov	r0, #0
47f347b4:	e581200c 	str	r2, [r1, #12]
47f347b8:	e5932024 	ldr	r2, [r3, #36]	@ 0x24
47f347bc:	e5812008 	str	r2, [r1, #8]
47f347c0:	e5932020 	ldr	r2, [r3, #32]
47f347c4:	e5812004 	str	r2, [r1, #4]
47f347c8:	e593301c 	ldr	r3, [r3, #28]
47f347cc:	e5813000 	str	r3, [r1]
47f347d0:	e8bd8010 	pop	{r4, pc}
47f347d4:	e3e00015 	mvn	r0, #21
47f347d8:	e12fff1e 	bx	lr
47f347dc:	92344000 	eorsls	r4, r4, #0
47f347e0:	47f62348 	ldrbmi	r2, [r6, r8, asr #6]!
47f347e4:	e3530001 	cmp	r3, #1
47f347e8:	93500007 	cmpls	r0, #7
47f347ec:	8a000019 	bhi	0x47f34858
47f347f0:	e92d4038 	push	{r3, r4, r5, lr}
47f347f4:	e3a0e01e 	mov	lr, #30
47f347f8:	e59f5060 	ldr	r5, [pc, #96]	@ 0x47f34860
47f347fc:	e595c064 	ldr	r12, [r5, #100]	@ 0x64
47f34800:	e59f4058 	ldr	r4, [pc, #88]	@ 0x47f34860
47f34804:	e21cc001 	ands	r12, r12, #1
47f34808:	1a000008 	bne	0x47f34830
47f3480c:	e1a01701 	lsl	r1, r1, #14
47f34810:	e1812202 	orr	r2, r1, r2, lsl #4
47f34814:	e1822000 	orr	r2, r2, r0
47f34818:	e1a0000c 	mov	r0, r12
47f3481c:	e1823183 	orr	r3, r2, r3, lsl #3
47f34820:	e5843068 	str	r3, [r4, #104]	@ 0x68
47f34824:	e3a03001 	mov	r3, #1
47f34828:	e5843064 	str	r3, [r4, #100]	@ 0x64
47f3482c:	e8bd8038 	pop	{r3, r4, r5, pc}
47f34830:	e25ee001 	subs	lr, lr, #1
47f34834:	1afffff0 	bne	0x47f347fc
47f34838:	e59f0024 	ldr	r0, [pc, #36]	@ 0x47f34864
47f3483c:	ebff5745 	bl	0x47f0a558
47f34840:	e59f2020 	ldr	r2, [pc, #32]	@ 0x47f34868
47f34844:	e3e0000a 	mvn	r0, #10
47f34848:	e5923004 	ldr	r3, [r2, #4]
47f3484c:	e2833001 	add	r3, r3, #1
47f34850:	e5823004 	str	r3, [r2, #4]
47f34854:	e8bd8038 	pop	{r3, r4, r5, pc}
47f34858:	e3e00015 	mvn	r0, #21
47f3485c:	e12fff1e 	bx	lr
47f34860:	92344000 	eorsls	r4, r4, #0
47f34864:	47f444ce 	ldrbmi	r4, [r4, lr, asr #9]!
47f34868:	47f62348 	ldrbmi	r2, [r6, r8, asr #6]!
47f3486c:	e92d401f 	push	{r0, r1, r2, r3, r4, lr}
47f34870:	e3a04000 	mov	r4, #0
47f34874:	e59f30b0 	ldr	r3, [pc, #176]	@ 0x47f3492c
47f34878:	e58d4008 	str	r4, [sp, #8]
47f3487c:	e58d400c 	str	r4, [sp, #12]
47f34880:	e88d0018 	stm	sp, {r3, r4}
47f34884:	e3a02000 	mov	r2, #0
47f34888:	e6ff0074 	uxth	r0, r4
47f3488c:	e1a0100d 	mov	r1, sp
47f34890:	ebffff8f 	bl	0x47f346d4
47f34894:	e2502000 	subs	r2, r0, #0
47f34898:	ba000018 	blt	0x47f34900
47f3489c:	e2844001 	add	r4, r4, #1
47f348a0:	e3540e19 	cmp	r4, #400	@ 0x190
47f348a4:	1afffff6 	bne	0x47f34884
47f348a8:	e3a04000 	mov	r4, #0
47f348ac:	e3a02002 	mov	r2, #2
47f348b0:	e6ff0074 	uxth	r0, r4
47f348b4:	e1a0100d 	mov	r1, sp
47f348b8:	ebffff85 	bl	0x47f346d4
47f348bc:	e2502000 	subs	r2, r0, #0
47f348c0:	ba00000e 	blt	0x47f34900
47f348c4:	e2844001 	add	r4, r4, #1
47f348c8:	e3540d06 	cmp	r4, #384	@ 0x180
47f348cc:	1afffff6 	bne	0x47f348ac
47f348d0:	e59f0058 	ldr	r0, [pc, #88]	@ 0x47f34930
47f348d4:	e3a04000 	mov	r4, #0
47f348d8:	e59f1054 	ldr	r1, [pc, #84]	@ 0x47f34934
47f348dc:	e3a03020 	mov	r3, #32
47f348e0:	e59f2050 	ldr	r2, [pc, #80]	@ 0x47f34938
47f348e4:	e88d000f 	stm	sp, {r0, r1, r2, r3}
47f348e8:	e3a02004 	mov	r2, #4
47f348ec:	e6ff0074 	uxth	r0, r4
47f348f0:	e1a0100d 	mov	r1, sp
47f348f4:	ebffff76 	bl	0x47f346d4
47f348f8:	e2502000 	subs	r2, r0, #0
47f348fc:	aa000004 	bge	0x47f34914
47f34900:	e59f0034 	ldr	r0, [pc, #52]	@ 0x47f3493c
47f34904:	e1a01004 	mov	r1, r4
47f34908:	ebff5712 	bl	0x47f0a558
47f3490c:	e3e00000 	mvn	r0, #0
47f34910:	ea000003 	b	0x47f34924
47f34914:	e2844001 	add	r4, r4, #1
47f34918:	e3540d06 	cmp	r4, #384	@ 0x180
47f3491c:	1afffff1 	bne	0x47f348e8
47f34920:	e3a00000 	mov	r0, #0
47f34924:	e28dd010 	add	sp, sp, #16
47f34928:	e8bd8010 	pop	{r4, pc}
47f3492c:	00800400 	addeq	r0, r0, r0, lsl #8
47f34930:	ff803fff 			@ <UNDEFINED> instruction: 0xff803fff
47f34934:	0100ff80 	smlabbeq	r0, r0, pc, pc	@ <UNPREDICTABLE>
47f34938:	00100200 	andseq	r0, r0, r0, lsl #4
47f3493c:	47f444e5 	ldrbmi	r4, [r4, r5, ror #9]!
47f34940:	e59f2018 	ldr	r2, [pc, #24]	@ 0x47f34960
47f34944:	e3500000 	cmp	r0, #0
47f34948:	e5923000 	ldr	r3, [r2]
47f3494c:	e3c3380f 	bic	r3, r3, #983040	@ 0xf0000
47f34950:	1383382f 	orrne	r3, r3, #3080192	@ 0x2f0000
47f34954:	03833602 	orreq	r3, r3, #2097152	@ 0x200000
47f34958:	e5823000 	str	r3, [r2]
47f3495c:	e12fff1e 	bx	lr
47f34960:	92350000 	eorsls	r0, r5, #0
47f34964:	e59f3070 	ldr	r3, [pc, #112]	@ 0x47f349dc
47f34968:	e92d4010 	push	{r4, lr}
47f3496c:	e1a04000 	mov	r4, r0
47f34970:	e59311fc 	ldr	r1, [r3, #508]	@ 0x1fc
47f34974:	e59f3064 	ldr	r3, [pc, #100]	@ 0x47f349e0
47f34978:	e2011003 	and	r1, r1, #3
47f3497c:	e3510000 	cmp	r1, #0
47f34980:	e5831000 	str	r1, [r3]
47f34984:	0a000001 	beq	0x47f34990
47f34988:	e59f0054 	ldr	r0, [pc, #84]	@ 0x47f349e4
47f3498c:	ebff56f1 	bl	0x47f0a558
47f34990:	e2841010 	add	r1, r4, #16
47f34994:	e1a00004 	mov	r0, r4
47f34998:	ebff322b 	bl	0x47f0124c
47f3499c:	e59f3044 	ldr	r3, [pc, #68]	@ 0x47f349e8
47f349a0:	e5931000 	ldr	r1, [r3]
47f349a4:	e59f2040 	ldr	r2, [pc, #64]	@ 0x47f349ec
47f349a8:	e1510002 	cmp	r1, r2
47f349ac:	02833831 	addeq	r3, r3, #3211264	@ 0x310000
47f349b0:	03a02001 	moveq	r2, #1
47f349b4:	05832064 	streq	r2, [r3, #100]	@ 0x64
47f349b8:	0a000005 	beq	0x47f349d4
47f349bc:	e5932000 	ldr	r2, [r3]
47f349c0:	e59f3028 	ldr	r3, [pc, #40]	@ 0x47f349f0
47f349c4:	e1520003 	cmp	r2, r3
47f349c8:	059f300c 	ldreq	r3, [pc, #12]	@ 0x47f349dc
47f349cc:	03a02001 	moveq	r2, #1
47f349d0:	05832054 	streq	r2, [r3, #84]	@ 0x54
47f349d4:	e3a00000 	mov	r0, #0
47f349d8:	e8bd8010 	pop	{r4, pc}
47f349dc:	92350000 	eorsls	r0, r5, #0
47f349e0:	47f62358 	ubfxmi	r2, r8, #6, #23
47f349e4:	47f4454b 	ldrbmi	r4, [r4, r11, asr #10]!
47f349e8:	92040000 	andls	r0, r4, #0
47f349ec:	27912810 			@ <UNDEFINED> instruction: 0x27912810
47f349f0:	27912710 			@ <UNDEFINED> instruction: 0x27912710
47f349f4:	e92d4008 	push	{r3, lr}
47f349f8:	e3a00001 	mov	r0, #1
47f349fc:	ebffffcf 	bl	0x47f34940
47f34a00:	e59f302c 	ldr	r3, [pc, #44]	@ 0x47f34a34
47f34a04:	e59f202c 	ldr	r2, [pc, #44]	@ 0x47f34a38
47f34a08:	e5832050 	str	r2, [r3, #80]	@ 0x50
47f34a0c:	e59f2028 	ldr	r2, [pc, #40]	@ 0x47f34a3c
47f34a10:	e5921000 	ldr	r1, [r2]
47f34a14:	e59f2024 	ldr	r2, [pc, #36]	@ 0x47f34a40
47f34a18:	e3a00000 	mov	r0, #0
47f34a1c:	e1510002 	cmp	r1, r2
47f34a20:	059f201c 	ldreq	r2, [pc, #28]	@ 0x47f34a44
47f34a24:	05832060 	streq	r2, [r3, #96]	@ 0x60
47f34a28:	e59f2018 	ldr	r2, [pc, #24]	@ 0x47f34a48
47f34a2c:	e583203c 	str	r2, [r3, #60]	@ 0x3c
47f34a30:	e8bd8008 	pop	{r3, pc}
47f34a34:	92350000 	eorsls	r0, r5, #0
47f34a38:	41b00000 	movsmi	r0, r0
47f34a3c:	92040000 	andls	r0, r4, #0
47f34a40:	27912810 			@ <UNDEFINED> instruction: 0x27912810
47f34a44:	41c00000 	bicmi	r0, r0, r0
47f34a48:	00400040 	subeq	r0, r0, r0, asr #32
47f34a4c:	e92d4010 	push	{r4, lr}
47f34a50:	ebffff85 	bl	0x47f3486c
47f34a54:	ebffffe6 	bl	0x47f349f4
47f34a58:	ebfffe23 	bl	0x47f342ec
47f34a5c:	e2504000 	subs	r4, r0, #0
47f34a60:	aa000004 	bge	0x47f34a78
47f34a64:	e1a01004 	mov	r1, r4
47f34a68:	e59f005c 	ldr	r0, [pc, #92]	@ 0x47f34acc
47f34a6c:	ebff56b9 	bl	0x47f0a558
47f34a70:	e1a00004 	mov	r0, r4
47f34a74:	e8bd8010 	pop	{r4, pc}
47f34a78:	ebfffeda 	bl	0x47f345e8
47f34a7c:	e59f204c 	ldr	r2, [pc, #76]	@ 0x47f34ad0
47f34a80:	e5921000 	ldr	r1, [r2]
47f34a84:	e59f3048 	ldr	r3, [pc, #72]	@ 0x47f34ad4
47f34a88:	e1510003 	cmp	r1, r3
47f34a8c:	e59f3044 	ldr	r3, [pc, #68]	@ 0x47f34ad8
47f34a90:	0a000003 	beq	0x47f34aa4
47f34a94:	e5921000 	ldr	r1, [r2]
47f34a98:	e59f203c 	ldr	r2, [pc, #60]	@ 0x47f34adc
47f34a9c:	e1510002 	cmp	r1, r2
47f34aa0:	1a000001 	bne	0x47f34aac
47f34aa4:	e59f2034 	ldr	r2, [pc, #52]	@ 0x47f34ae0
47f34aa8:	e58320f0 	str	r2, [r3, #240]	@ 0xf0
47f34aac:	e3a02010 	mov	r2, #16
47f34ab0:	e5832004 	str	r2, [r3, #4]
47f34ab4:	eb0002bb 	bl	0x47f355a8
47f34ab8:	eb0002ef 	bl	0x47f3567c
47f34abc:	e59f0020 	ldr	r0, [pc, #32]	@ 0x47f34ae4
47f34ac0:	ebff56a4 	bl	0x47f0a558
47f34ac4:	e3a00000 	mov	r0, #0
47f34ac8:	e8bd8010 	pop	{r4, pc}
47f34acc:	47f4455c 	ubfxmi	r4, r12, #10, #21
47f34ad0:	92040000 	andls	r0, r4, #0
47f34ad4:	27912810 			@ <UNDEFINED> instruction: 0x27912810
47f34ad8:	92340000 	eorsls	r0, r4, #0
47f34adc:	27912710 			@ <UNDEFINED> instruction: 0x27912710
47f34ae0:	41a00000 	movmi	r0, r0
47f34ae4:	47f44846 	ldrbmi	r4, [r4, r6, asr #16]!
47f34ae8:	e59f3048 	ldr	r3, [pc, #72]	@ 0x47f34b38
47f34aec:	e5931000 	ldr	r1, [r3]
47f34af0:	e59f2044 	ldr	r2, [pc, #68]	@ 0x47f34b3c
47f34af4:	e1510002 	cmp	r1, r2
47f34af8:	02833831 	addeq	r3, r3, #3211264	@ 0x310000
47f34afc:	05933068 	ldreq	r3, [r3, #104]	@ 0x68
47f34b00:	0a000005 	beq	0x47f34b1c
47f34b04:	e5932000 	ldr	r2, [r3]
47f34b08:	e59f3030 	ldr	r3, [pc, #48]	@ 0x47f34b40
47f34b0c:	e1520003 	cmp	r2, r3
47f34b10:	059f302c 	ldreq	r3, [pc, #44]	@ 0x47f34b44
47f34b14:	13a03000 	movne	r3, #0
47f34b18:	05933058 	ldreq	r3, [r3, #88]	@ 0x58
47f34b1c:	e59f1024 	ldr	r1, [pc, #36]	@ 0x47f34b48
47f34b20:	e6ff3073 	uxth	r3, r3
47f34b24:	e3a00000 	mov	r0, #0
47f34b28:	e5912000 	ldr	r2, [r1]
47f34b2c:	e0633002 	rsb	r3, r3, r2
47f34b30:	e5813000 	str	r3, [r1]
47f34b34:	e12fff1e 	bx	lr
47f34b38:	92040000 	andls	r0, r4, #0
47f34b3c:	27912810 			@ <UNDEFINED> instruction: 0x27912810
47f34b40:	27912710 			@ <UNDEFINED> instruction: 0x27912710
47f34b44:	92350000 	eorsls	r0, r5, #0
47f34b48:	47f6235c 	ubfxmi	r2, r12, #6, #23
47f34b4c:	e3510040 	cmp	r1, #64	@ 0x40
47f34b50:	e92d4070 	push	{r4, r5, r6, lr}
47f34b54:	e1a06000 	mov	r6, r0
47f34b58:	31a05001 	movcc	r5, r1
47f34b5c:	23a05040 	movcs	r5, #64	@ 0x40
47f34b60:	e3a04000 	mov	r4, #0
47f34b64:	e1540005 	cmp	r4, r5
47f34b68:	0a000009 	beq	0x47f34b94
47f34b6c:	e59f002c 	ldr	r0, [pc, #44]	@ 0x47f34ba0
47f34b70:	e7d61004 	ldrb	r1, [r6, r4]
47f34b74:	ebff5677 	bl	0x47f0a558
47f34b78:	e204300f 	and	r3, r4, #15
47f34b7c:	e353000f 	cmp	r3, #15
47f34b80:	1a000001 	bne	0x47f34b8c
47f34b84:	e59f0018 	ldr	r0, [pc, #24]	@ 0x47f34ba4
47f34b88:	ebff5672 	bl	0x47f0a558
47f34b8c:	e2844001 	add	r4, r4, #1
47f34b90:	eafffff3 	b	0x47f34b64
47f34b94:	e59f0008 	ldr	r0, [pc, #8]	@ 0x47f34ba4
47f34b98:	e8bd4070 	pop	{r4, r5, r6, lr}
47f34b9c:	eaff566d 	b	0x47f0a558
47f34ba0:	47f42f84 	ldrbmi	r2, [r4, r4, lsl #31]!
47f34ba4:	47f3ad6e 	ldrbmi	r10, [r3, lr, ror #26]!
47f34ba8:	e92d4008 	push	{r3, lr}
47f34bac:	ebfffdba 	bl	0x47f3429c
47f34bb0:	e3a00000 	mov	r0, #0
47f34bb4:	eb00033d 	bl	0x47f358b0
47f34bb8:	e3a00001 	mov	r0, #1
47f34bbc:	eb00033b 	bl	0x47f358b0
47f34bc0:	e3a00002 	mov	r0, #2
47f34bc4:	eb000339 	bl	0x47f358b0
47f34bc8:	e3a00003 	mov	r0, #3
47f34bcc:	eb000337 	bl	0x47f358b0
47f34bd0:	e3a00000 	mov	r0, #0
47f34bd4:	e8bd8008 	pop	{r3, pc}
47f34bd8:	e92d4008 	push	{r3, lr}
47f34bdc:	e3a00064 	mov	r0, #100	@ 0x64
47f34be0:	ebffc743 	bl	0x47f268f4
47f34be4:	e3a00000 	mov	r0, #0
47f34be8:	eb0003c4 	bl	0x47f35b00
47f34bec:	e3a00001 	mov	r0, #1
47f34bf0:	eb0003c2 	bl	0x47f35b00
47f34bf4:	e3a00002 	mov	r0, #2
47f34bf8:	eb0003c0 	bl	0x47f35b00
47f34bfc:	e3a00003 	mov	r0, #3
47f34c00:	e8bd4008 	pop	{r3, lr}
47f34c04:	ea0003bd 	b	0x47f35b00
47f34c08:	e5d03007 	ldrb	r3, [r0, #7]
47f34c0c:	e92d4037 	push	{r0, r1, r2, r4, r5, lr}
47f34c10:	e1a04000 	mov	r4, r0
47f34c14:	e5d05008 	ldrb	r5, [r0, #8]
47f34c18:	e1a030a3 	lsr	r3, r3, #1
47f34c1c:	e1a01004 	mov	r1, r4
47f34c20:	e1835385 	orr	r5, r3, r5, lsl #7
47f34c24:	e5903008 	ldr	r3, [r0, #8]
47f34c28:	e58d3000 	str	r3, [sp]
47f34c2c:	e590300c 	ldr	r3, [r0, #12]
47f34c30:	e59f0034 	ldr	r0, [pc, #52]	@ 0x47f34c6c
47f34c34:	e58d3004 	str	r3, [sp, #4]
47f34c38:	e894000c 	ldm	r4, {r2, r3}
47f34c3c:	ebff5645 	bl	0x47f0a558
47f34c40:	e59f1028 	ldr	r1, [pc, #40]	@ 0x47f34c70
47f34c44:	e1d430bc 	ldrh	r3, [r4, #12]
47f34c48:	e1d420b4 	ldrh	r2, [r4, #4]
47f34c4c:	e5911004 	ldr	r1, [r1, #4]
47f34c50:	e1a03123 	lsr	r3, r3, #2
47f34c54:	e59f0018 	ldr	r0, [pc, #24]	@ 0x47f34c74
47f34c58:	e58d1000 	str	r1, [sp]
47f34c5c:	e1a01005 	mov	r1, r5
47f34c60:	ebff563c 	bl	0x47f0a558
47f34c64:	e28dd00c 	add	sp, sp, #12
47f34c68:	e8bd8030 	pop	{r4, r5, pc}
47f34c6c:	47f4485d 	ubfxmi	r4, sp, #16, #21
47f34c70:	47f6235c 	ubfxmi	r2, r12, #6, #23
47f34c74:	47f44881 	ldrbmi	r4, [r4, r1, lsl #17]!
47f34c78:	e5903008 	ldr	r3, [r0, #8]
47f34c7c:	e92d4037 	push	{r0, r1, r2, r4, r5, lr}
47f34c80:	e1a04000 	mov	r4, r0
47f34c84:	e1d050b8 	ldrh	r5, [r0, #8]
47f34c88:	e1a01004 	mov	r1, r4
47f34c8c:	e58d3000 	str	r3, [sp]
47f34c90:	e590300c 	ldr	r3, [r0, #12]
47f34c94:	e7ee5055 	ubfx	r5, r5, #0, #15
47f34c98:	e59f0038 	ldr	r0, [pc, #56]	@ 0x47f34cd8
47f34c9c:	e58d3004 	str	r3, [sp, #4]
47f34ca0:	e894000c 	ldm	r4, {r2, r3}
47f34ca4:	ebff562b 	bl	0x47f0a558
47f34ca8:	e59f102c 	ldr	r1, [pc, #44]	@ 0x47f34cdc
47f34cac:	e1d430bc 	ldrh	r3, [r4, #12]
47f34cb0:	e1d420b4 	ldrh	r2, [r4, #4]
47f34cb4:	e5911008 	ldr	r1, [r1, #8]
47f34cb8:	e7eb2052 	ubfx	r2, r2, #0, #12
47f34cbc:	e1a03123 	lsr	r3, r3, #2
47f34cc0:	e59f0018 	ldr	r0, [pc, #24]	@ 0x47f34ce0
47f34cc4:	e58d1000 	str	r1, [sp]
47f34cc8:	e1a01005 	mov	r1, r5
47f34ccc:	ebff5621 	bl	0x47f0a558
47f34cd0:	e28dd00c 	add	sp, sp, #12
47f34cd4:	e8bd8030 	pop	{r4, r5, pc}
47f34cd8:	47f4485d 	ubfxmi	r4, sp, #16, #21
47f34cdc:	47f6235c 	ubfxmi	r2, r12, #6, #23
47f34ce0:	47f448ab 	ldrbmi	r4, [r4, r11, lsr #17]!
47f34ce4:	e92d4ef0 	push	{r4, r5, r6, r7, r9, r10, r11, lr}
47f34ce8:	e24dd018 	sub	sp, sp, #24
47f34cec:	e59f5358 	ldr	r5, [pc, #856]	@ 0x47f3504c
47f34cf0:	e3a07007 	mov	r7, #7
47f34cf4:	e59f3354 	ldr	r3, [pc, #852]	@ 0x47f35050
47f34cf8:	e0873003 	add	r3, r7, r3
47f34cfc:	e1a03103 	lsl	r3, r3, #2
47f34d00:	e58d3014 	str	r3, [sp, #20]
47f34d04:	e5933000 	ldr	r3, [r3]
47f34d08:	e6ff3073 	uxth	r3, r3
47f34d0c:	e58d3008 	str	r3, [sp, #8]
47f34d10:	e3530000 	cmp	r3, #0
47f34d14:	0a0000c5 	beq	0x47f35030
47f34d18:	e59f3334 	ldr	r3, [pc, #820]	@ 0x47f35054
47f34d1c:	e593204c 	ldr	r2, [r3, #76]	@ 0x4c
47f34d20:	e58d300c 	str	r3, [sp, #12]
47f34d24:	e3520000 	cmp	r2, #0
47f34d28:	da000003 	ble	0x47f34d3c
47f34d2c:	e59f0324 	ldr	r0, [pc, #804]	@ 0x47f35058
47f34d30:	e1a01007 	mov	r1, r7
47f34d34:	e59d2008 	ldr	r2, [sp, #8]
47f34d38:	ebff5606 	bl	0x47f0a558
47f34d3c:	e59f3318 	ldr	r3, [pc, #792]	@ 0x47f3505c
47f34d40:	e5932000 	ldr	r2, [r3]
47f34d44:	e59f1314 	ldr	r1, [pc, #788]	@ 0x47f35060
47f34d48:	e1520001 	cmp	r2, r1
47f34d4c:	1a00005d 	bne	0x47f34ec8
47f34d50:	e59fb2fc 	ldr	r11, [pc, #764]	@ 0x47f35054
47f34d54:	e3a03000 	mov	r3, #0
47f34d58:	e58d3010 	str	r3, [sp, #16]
47f34d5c:	e595303c 	ldr	r3, [r5, #60]	@ 0x3c
47f34d60:	e5954038 	ldr	r4, [r5, #56]	@ 0x38
47f34d64:	e0844203 	add	r4, r4, r3, lsl #4
47f34d68:	e2833001 	add	r3, r3, #1
47f34d6c:	e3530b01 	cmp	r3, #1024	@ 0x400
47f34d70:	e2841010 	add	r1, r4, #16
47f34d74:	e1a00004 	mov	r0, r4
47f34d78:	e585303c 	str	r3, [r5, #60]	@ 0x3c
47f34d7c:	23a03000 	movcs	r3, #0
47f34d80:	2585303c 	strcs	r3, [r5, #60]	@ 0x3c
47f34d84:	ebff3130 	bl	0x47f0124c
47f34d88:	e5d43007 	ldrb	r3, [r4, #7]
47f34d8c:	e5d46008 	ldrb	r6, [r4, #8]
47f34d90:	e1a030a3 	lsr	r3, r3, #1
47f34d94:	e1836386 	orr	r6, r3, r6, lsl #7
47f34d98:	e3560b02 	cmp	r6, #2048	@ 0x800
47f34d9c:	ba00000a 	blt	0x47f34dcc
47f34da0:	e1a01006 	mov	r1, r6
47f34da4:	e59f02b8 	ldr	r0, [pc, #696]	@ 0x47f35064
47f34da8:	ebff55ea 	bl	0x47f0a558
47f34dac:	e1a00004 	mov	r0, r4
47f34db0:	ebffff94 	bl	0x47f34c08
47f34db4:	e3a01000 	mov	r1, #0
47f34db8:	e6ef0077 	uxtb	r0, r7
47f34dbc:	e3a02001 	mov	r2, #1
47f34dc0:	e1a03001 	mov	r3, r1
47f34dc4:	ebfffe86 	bl	0x47f347e4
47f34dc8:	ea000030 	b	0x47f34e90
47f34dcc:	e1a0c586 	lsl	r12, r6, #11
47f34dd0:	e1d490bc 	ldrh	r9, [r4, #12]
47f34dd4:	e28ca441 	add	r10, r12, #1090519040	@ 0x41000000
47f34dd8:	e28aa010 	add	r10, r10, #16
47f34ddc:	e1a09129 	lsr	r9, r9, #2
47f34de0:	e1a0000a 	mov	r0, r10
47f34de4:	e08a1009 	add	r1, r10, r9
47f34de8:	ebff3117 	bl	0x47f0124c
47f34dec:	e59b304c 	ldr	r3, [r11, #76]	@ 0x4c
47f34df0:	e3530000 	cmp	r3, #0
47f34df4:	da00000d 	ble	0x47f34e30
47f34df8:	e1a00004 	mov	r0, r4
47f34dfc:	ebffff81 	bl	0x47f34c08
47f34e00:	e1d430b4 	ldrh	r3, [r4, #4]
47f34e04:	e1a01009 	mov	r1, r9
47f34e08:	e1a02006 	mov	r2, r6
47f34e0c:	e58da000 	str	r10, [sp]
47f34e10:	e59f0250 	ldr	r0, [pc, #592]	@ 0x47f35068
47f34e14:	ebff55cf 	bl	0x47f0a558
47f34e18:	e1a0000a 	mov	r0, r10
47f34e1c:	e1a01009 	mov	r1, r9
47f34e20:	ebffff49 	bl	0x47f34b4c
47f34e24:	e59b304c 	ldr	r3, [r11, #76]	@ 0x4c
47f34e28:	e2433001 	sub	r3, r3, #1
47f34e2c:	e58b304c 	str	r3, [r11, #76]	@ 0x4c
47f34e30:	e59d300c 	ldr	r3, [sp, #12]
47f34e34:	e1a0000a 	mov	r0, r10
47f34e38:	e59d200c 	ldr	r2, [sp, #12]
47f34e3c:	e1a01009 	mov	r1, r9
47f34e40:	e5933004 	ldr	r3, [r3, #4]
47f34e44:	e2833001 	add	r3, r3, #1
47f34e48:	e5823004 	str	r3, [r2, #4]
47f34e4c:	ebffe3c8 	bl	0x47f2dd74
47f34e50:	e5d40003 	ldrb	r0, [r4, #3]
47f34e54:	e3a01000 	mov	r1, #0
47f34e58:	e3a02001 	mov	r2, #1
47f34e5c:	e7e20150 	ubfx	r0, r0, #2, #3
47f34e60:	e1a03001 	mov	r3, r1
47f34e64:	ebfffe5e 	bl	0x47f347e4
47f34e68:	e3500000 	cmp	r0, #0
47f34e6c:	aa000001 	bge	0x47f34e78
47f34e70:	e59f01f4 	ldr	r0, [pc, #500]	@ 0x47f3506c
47f34e74:	ebff55b7 	bl	0x47f0a558
47f34e78:	e1a00006 	mov	r0, r6
47f34e7c:	ebfffdfa 	bl	0x47f3466c
47f34e80:	e3500000 	cmp	r0, #0
47f34e84:	aa000001 	bge	0x47f34e90
47f34e88:	e59f01e0 	ldr	r0, [pc, #480]	@ 0x47f35070
47f34e8c:	ebff55b1 	bl	0x47f0a558
47f34e90:	e59d3010 	ldr	r3, [sp, #16]
47f34e94:	e59d2008 	ldr	r2, [sp, #8]
47f34e98:	e2833001 	add	r3, r3, #1
47f34e9c:	e58d3010 	str	r3, [sp, #16]
47f34ea0:	e1530002 	cmp	r3, r2
47f34ea4:	baffffac 	blt	0x47f34d5c
47f34ea8:	e59d3014 	ldr	r3, [sp, #20]
47f34eac:	e5933000 	ldr	r3, [r3]
47f34eb0:	e6ff3073 	uxth	r3, r3
47f34eb4:	e3530000 	cmp	r3, #0
47f34eb8:	0a00005c 	beq	0x47f35030
47f34ebc:	e3a00001 	mov	r0, #1
47f34ec0:	ebffc68b 	bl	0x47f268f4
47f34ec4:	ea000059 	b	0x47f35030
47f34ec8:	e5933000 	ldr	r3, [r3]
47f34ecc:	e59f21a0 	ldr	r2, [pc, #416]	@ 0x47f35074
47f34ed0:	e1530002 	cmp	r3, r2
47f34ed4:	1afffff3 	bne	0x47f34ea8
47f34ed8:	e59fb174 	ldr	r11, [pc, #372]	@ 0x47f35054
47f34edc:	e3a03000 	mov	r3, #0
47f34ee0:	e58d3010 	str	r3, [sp, #16]
47f34ee4:	e595303c 	ldr	r3, [r5, #60]	@ 0x3c
47f34ee8:	e5954038 	ldr	r4, [r5, #56]	@ 0x38
47f34eec:	e0844203 	add	r4, r4, r3, lsl #4
47f34ef0:	e2833001 	add	r3, r3, #1
47f34ef4:	e3530b01 	cmp	r3, #1024	@ 0x400
47f34ef8:	e2841010 	add	r1, r4, #16
47f34efc:	e1a00004 	mov	r0, r4
47f34f00:	e585303c 	str	r3, [r5, #60]	@ 0x3c
47f34f04:	23a03000 	movcs	r3, #0
47f34f08:	2585303c 	strcs	r3, [r5, #60]	@ 0x3c
47f34f0c:	ebff30ce 	bl	0x47f0124c
47f34f10:	e1d460b8 	ldrh	r6, [r4, #8]
47f34f14:	e7ee6056 	ubfx	r6, r6, #0, #15
47f34f18:	e3560901 	cmp	r6, #16384	@ 0x4000
47f34f1c:	ba00000a 	blt	0x47f34f4c
47f34f20:	e1a01006 	mov	r1, r6
47f34f24:	e59f0138 	ldr	r0, [pc, #312]	@ 0x47f35064
47f34f28:	ebff558a 	bl	0x47f0a558
47f34f2c:	e1a00004 	mov	r0, r4
47f34f30:	ebffff50 	bl	0x47f34c78
47f34f34:	e3a01000 	mov	r1, #0
47f34f38:	e6ef0077 	uxtb	r0, r7
47f34f3c:	e3a02001 	mov	r2, #1
47f34f40:	e1a03001 	mov	r3, r1
47f34f44:	ebfffe26 	bl	0x47f347e4
47f34f48:	ea000031 	b	0x47f35014
47f34f4c:	e1a0c586 	lsl	r12, r6, #11
47f34f50:	e1d490bc 	ldrh	r9, [r4, #12]
47f34f54:	e28ca441 	add	r10, r12, #1090519040	@ 0x41000000
47f34f58:	e28aa010 	add	r10, r10, #16
47f34f5c:	e1a09129 	lsr	r9, r9, #2
47f34f60:	e1a0000a 	mov	r0, r10
47f34f64:	e08a1009 	add	r1, r10, r9
47f34f68:	ebff30b7 	bl	0x47f0124c
47f34f6c:	e59b304c 	ldr	r3, [r11, #76]	@ 0x4c
47f34f70:	e3530000 	cmp	r3, #0
47f34f74:	da00000e 	ble	0x47f34fb4
47f34f78:	e1a00004 	mov	r0, r4
47f34f7c:	ebffff3d 	bl	0x47f34c78
47f34f80:	e1d430b4 	ldrh	r3, [r4, #4]
47f34f84:	e1a01009 	mov	r1, r9
47f34f88:	e1a02006 	mov	r2, r6
47f34f8c:	e7eb3053 	ubfx	r3, r3, #0, #12
47f34f90:	e58da000 	str	r10, [sp]
47f34f94:	e59f00cc 	ldr	r0, [pc, #204]	@ 0x47f35068
47f34f98:	ebff556e 	bl	0x47f0a558
47f34f9c:	e1a0000a 	mov	r0, r10
47f34fa0:	e1a01009 	mov	r1, r9
47f34fa4:	ebfffee8 	bl	0x47f34b4c
47f34fa8:	e59b304c 	ldr	r3, [r11, #76]	@ 0x4c
47f34fac:	e2433001 	sub	r3, r3, #1
47f34fb0:	e58b304c 	str	r3, [r11, #76]	@ 0x4c
47f34fb4:	e59d300c 	ldr	r3, [sp, #12]
47f34fb8:	e1a0000a 	mov	r0, r10
47f34fbc:	e59d200c 	ldr	r2, [sp, #12]
47f34fc0:	e1a01009 	mov	r1, r9
47f34fc4:	e5933008 	ldr	r3, [r3, #8]
47f34fc8:	e2833001 	add	r3, r3, #1
47f34fcc:	e5823008 	str	r3, [r2, #8]
47f34fd0:	ebffe367 	bl	0x47f2dd74
47f34fd4:	e5d40003 	ldrb	r0, [r4, #3]
47f34fd8:	e3a01000 	mov	r1, #0
47f34fdc:	e3a02001 	mov	r2, #1
47f34fe0:	e7e20150 	ubfx	r0, r0, #2, #3
47f34fe4:	e1a03001 	mov	r3, r1
47f34fe8:	ebfffdfd 	bl	0x47f347e4
47f34fec:	e3500000 	cmp	r0, #0
47f34ff0:	aa000001 	bge	0x47f34ffc
47f34ff4:	e59f0070 	ldr	r0, [pc, #112]	@ 0x47f3506c
47f34ff8:	ebff5556 	bl	0x47f0a558
47f34ffc:	e1a00006 	mov	r0, r6
47f35000:	ebfffd99 	bl	0x47f3466c
47f35004:	e3500000 	cmp	r0, #0
47f35008:	aa000001 	bge	0x47f35014
47f3500c:	e59f005c 	ldr	r0, [pc, #92]	@ 0x47f35070
47f35010:	ebff5550 	bl	0x47f0a558
47f35014:	e59d3010 	ldr	r3, [sp, #16]
47f35018:	e59d2008 	ldr	r2, [sp, #8]
47f3501c:	e2833001 	add	r3, r3, #1
47f35020:	e58d3010 	str	r3, [sp, #16]
47f35024:	e1530002 	cmp	r3, r2
47f35028:	baffffad 	blt	0x47f34ee4
47f3502c:	eaffff9d 	b	0x47f34ea8
47f35030:	e2477001 	sub	r7, r7, #1
47f35034:	e2455008 	sub	r5, r5, #8
47f35038:	e3770001 	cmn	r7, #1
47f3503c:	1affff2c 	bne	0x47f34cf4
47f35040:	e3a00000 	mov	r0, #0
47f35044:	e28dd018 	add	sp, sp, #24
47f35048:	e8bd8ef0 	pop	{r4, r5, r6, r7, r9, r10, r11, pc}
47f3504c:	47f62368 	ldrbmi	r2, [r6, r8, ror #6]!
47f35050:	248d4040 	strcs	r4, [sp], #64	@ 0x40
47f35054:	47f6235c 	ubfxmi	r2, r12, #6, #23
47f35058:	47f445c1 	ldrbmi	r4, [r4, r1, asr #11]!
47f3505c:	92040000 	andls	r0, r4, #0
47f35060:	27912810 			@ <UNDEFINED> instruction: 0x27912810
47f35064:	47f448d7 	ubfxmi	r4, r7, #17, #21
47f35068:	47f445e1 	ldrbmi	r4, [r4, r1, ror #11]!
47f3506c:	47f44608 	ldrbmi	r4, [r4, r8, lsl #12]!
47f35070:	47f44620 	ldrbmi	r4, [r4, r0, lsr #12]!
47f35074:	27912710 			@ <UNDEFINED> instruction: 0x27912710
47f35078:	e12fff1e 	bx	lr
47f3507c:	e59f3070 	ldr	r3, [pc, #112]	@ 0x47f350f4
47f35080:	e92d4037 	push	{r0, r1, r2, r4, r5, lr}
47f35084:	e1a04000 	mov	r4, r0
47f35088:	e5931050 	ldr	r1, [r3, #80]	@ 0x50
47f3508c:	e59f0064 	ldr	r0, [pc, #100]	@ 0x47f350f8
47f35090:	ebff5530 	bl	0x47f0a558
47f35094:	e5943008 	ldr	r3, [r4, #8]
47f35098:	e1a01004 	mov	r1, r4
47f3509c:	e59f0058 	ldr	r0, [pc, #88]	@ 0x47f350fc
47f350a0:	e1d450b8 	ldrh	r5, [r4, #8]
47f350a4:	e58d3000 	str	r3, [sp]
47f350a8:	e594300c 	ldr	r3, [r4, #12]
47f350ac:	e7ee5055 	ubfx	r5, r5, #0, #15
47f350b0:	e58d3004 	str	r3, [sp, #4]
47f350b4:	e894000c 	ldm	r4, {r2, r3}
47f350b8:	ebff5526 	bl	0x47f0a558
47f350bc:	e5d4100b 	ldrb	r1, [r4, #11]
47f350c0:	e1d430bc 	ldrh	r3, [r4, #12]
47f350c4:	e1d420b4 	ldrh	r2, [r4, #4]
47f350c8:	e1a013a1 	lsr	r1, r1, #7
47f350cc:	e58d1000 	str	r1, [sp]
47f350d0:	e5d4100a 	ldrb	r1, [r4, #10]
47f350d4:	e7eb2052 	ubfx	r2, r2, #0, #12
47f350d8:	e1a03123 	lsr	r3, r3, #2
47f350dc:	e59f001c 	ldr	r0, [pc, #28]	@ 0x47f35100
47f350e0:	e58d1004 	str	r1, [sp, #4]
47f350e4:	e1a01005 	mov	r1, r5
47f350e8:	ebff551a 	bl	0x47f0a558
47f350ec:	e28dd00c 	add	sp, sp, #12
47f350f0:	e8bd8030 	pop	{r4, r5, pc}
47f350f4:	47f6235c 	ubfxmi	r2, r12, #6, #23
47f350f8:	47f448e9 	ldrbmi	r4, [r4, r9, ror #17]!
47f350fc:	47f44902 	ldrbmi	r4, [r4, r2, lsl #18]!
47f35100:	47f44926 	ldrbmi	r4, [r4, r6, lsr #18]!
47f35104:	e92d42f0 	push	{r4, r5, r6, r7, r9, lr}
47f35108:	e1a09000 	mov	r9, r0
47f3510c:	e1a07001 	mov	r7, r1
47f35110:	e1a04002 	mov	r4, r2
47f35114:	ebfffd38 	bl	0x47f345fc
47f35118:	e2506000 	subs	r6, r0, #0
47f3511c:	aa000002 	bge	0x47f3512c
47f35120:	e59f00ec 	ldr	r0, [pc, #236]	@ 0x47f35214
47f35124:	ebff550b 	bl	0x47f0a558
47f35128:	ea000004 	b	0x47f35140
47f3512c:	e3560b02 	cmp	r6, #2048	@ 0x800
47f35130:	ba000004 	blt	0x47f35148
47f35134:	e59f00dc 	ldr	r0, [pc, #220]	@ 0x47f35218
47f35138:	e1a01006 	mov	r1, r6
47f3513c:	ebff5505 	bl	0x47f0a558
47f35140:	e3e00000 	mvn	r0, #0
47f35144:	e8bd82f0 	pop	{r4, r5, r6, r7, r9, pc}
47f35148:	e1a05586 	lsl	r5, r6, #11
47f3514c:	e1a01009 	mov	r1, r9
47f35150:	e2855441 	add	r5, r5, #1090519040	@ 0x41000000
47f35154:	e1a02007 	mov	r2, r7
47f35158:	e2855010 	add	r5, r5, #16
47f3515c:	e59f90b8 	ldr	r9, [pc, #184]	@ 0x47f3521c
47f35160:	e1a00005 	mov	r0, r5
47f35164:	ebffc55e 	bl	0x47f266e4
47f35168:	e5d43007 	ldrb	r3, [r4, #7]
47f3516c:	e7ed2057 	ubfx	r2, r7, #0, #14
47f35170:	e7c73096 	bfi	r3, r6, #1, #7
47f35174:	e5c43007 	strb	r3, [r4, #7]
47f35178:	e1a033c6 	asr	r3, r6, #7
47f3517c:	e5c43008 	strb	r3, [r4, #8]
47f35180:	e1d430bc 	ldrh	r3, [r4, #12]
47f35184:	e7cf3112 	bfi	r3, r2, #2, #14
47f35188:	e1c430bc 	strh	r3, [r4, #12]
47f3518c:	e5943008 	ldr	r3, [r4, #8]
47f35190:	e7d63492 	bfi	r3, r2, #9, #14
47f35194:	e5843008 	str	r3, [r4, #8]
47f35198:	e3a02010 	mov	r2, #16
47f3519c:	e1a03c23 	lsr	r3, r3, #24
47f351a0:	e7c73092 	bfi	r3, r2, #1, #7
47f351a4:	e5c4300b 	strb	r3, [r4, #11]
47f351a8:	e599304c 	ldr	r3, [r9, #76]	@ 0x4c
47f351ac:	e3530000 	cmp	r3, #0
47f351b0:	da00000a 	ble	0x47f351e0
47f351b4:	e1a03005 	mov	r3, r5
47f351b8:	e1a01007 	mov	r1, r7
47f351bc:	e1a02006 	mov	r2, r6
47f351c0:	e59f0058 	ldr	r0, [pc, #88]	@ 0x47f35220
47f351c4:	ebff54e3 	bl	0x47f0a558
47f351c8:	e1a00005 	mov	r0, r5
47f351cc:	e1a01007 	mov	r1, r7
47f351d0:	ebfffe5d 	bl	0x47f34b4c
47f351d4:	e599304c 	ldr	r3, [r9, #76]	@ 0x4c
47f351d8:	e2433001 	sub	r3, r3, #1
47f351dc:	e589304c 	str	r3, [r9, #76]	@ 0x4c
47f351e0:	e1a00005 	mov	r0, r5
47f351e4:	e0851007 	add	r1, r5, r7
47f351e8:	ebff3017 	bl	0x47f0124c
47f351ec:	e1a00004 	mov	r0, r4
47f351f0:	ebfffddb 	bl	0x47f34964
47f351f4:	e3500000 	cmp	r0, #0
47f351f8:	aa000003 	bge	0x47f3520c
47f351fc:	e59f0020 	ldr	r0, [pc, #32]	@ 0x47f35224
47f35200:	ebff54d4 	bl	0x47f0a558
47f35204:	e3e00001 	mvn	r0, #1
47f35208:	e8bd82f0 	pop	{r4, r5, r6, r7, r9, pc}
47f3520c:	e3a00000 	mov	r0, #0
47f35210:	e8bd82f0 	pop	{r4, r5, r6, r7, r9, pc}
47f35214:	47f4466c 	ldrbmi	r4, [r4, r12, ror #12]!
47f35218:	47f44956 	ubfxmi	r4, r6, #18, #21
47f3521c:	47f6235c 	ubfxmi	r2, r12, #6, #23
47f35220:	47f44699 			@ <UNDEFINED> instruction: 0x47f44699
47f35224:	47f446b6 			@ <UNDEFINED> instruction: 0x47f446b6
47f35228:	e92d42f0 	push	{r4, r5, r6, r7, r9, lr}
47f3522c:	e1a09000 	mov	r9, r0
47f35230:	e1a06001 	mov	r6, r1
47f35234:	e1a04002 	mov	r4, r2
47f35238:	ebfffcef 	bl	0x47f345fc
47f3523c:	e2507000 	subs	r7, r0, #0
47f35240:	aa000002 	bge	0x47f35250
47f35244:	e59f00f0 	ldr	r0, [pc, #240]	@ 0x47f3533c
47f35248:	ebff54c2 	bl	0x47f0a558
47f3524c:	ea000004 	b	0x47f35264
47f35250:	e3570901 	cmp	r7, #16384	@ 0x4000
47f35254:	ba000004 	blt	0x47f3526c
47f35258:	e59f00e0 	ldr	r0, [pc, #224]	@ 0x47f35340
47f3525c:	e1a01007 	mov	r1, r7
47f35260:	ebff54bc 	bl	0x47f0a558
47f35264:	e3e00000 	mvn	r0, #0
47f35268:	e8bd82f0 	pop	{r4, r5, r6, r7, r9, pc}
47f3526c:	e1a05587 	lsl	r5, r7, #11
47f35270:	e1a01009 	mov	r1, r9
47f35274:	e2855441 	add	r5, r5, #1090519040	@ 0x41000000
47f35278:	e1a02006 	mov	r2, r6
47f3527c:	e2855010 	add	r5, r5, #16
47f35280:	e59f90bc 	ldr	r9, [pc, #188]	@ 0x47f35344
47f35284:	e1a00005 	mov	r0, r5
47f35288:	ebffc515 	bl	0x47f266e4
47f3528c:	e1d430b8 	ldrh	r3, [r4, #8]
47f35290:	e3a02010 	mov	r2, #16
47f35294:	e7ce3017 	bfi	r3, r7, #0, #15
47f35298:	e1c430b8 	strh	r3, [r4, #8]
47f3529c:	e5d4300b 	ldrb	r3, [r4, #11]
47f352a0:	e3833080 	orr	r3, r3, #128	@ 0x80
47f352a4:	e5c4300b 	strb	r3, [r4, #11]
47f352a8:	e1d430bc 	ldrh	r3, [r4, #12]
47f352ac:	e7cf3116 	bfi	r3, r6, #2, #14
47f352b0:	e1c430bc 	strh	r3, [r4, #12]
47f352b4:	e3a03000 	mov	r3, #0
47f352b8:	e5c4300a 	strb	r3, [r4, #10]
47f352bc:	e5d43007 	ldrb	r3, [r4, #7]
47f352c0:	e7c73092 	bfi	r3, r2, #1, #7
47f352c4:	e5c43007 	strb	r3, [r4, #7]
47f352c8:	e599304c 	ldr	r3, [r9, #76]	@ 0x4c
47f352cc:	e3530000 	cmp	r3, #0
47f352d0:	da00000c 	ble	0x47f35308
47f352d4:	e1a03005 	mov	r3, r5
47f352d8:	e1a01006 	mov	r1, r6
47f352dc:	e1a02007 	mov	r2, r7
47f352e0:	e59f0060 	ldr	r0, [pc, #96]	@ 0x47f35348
47f352e4:	ebff549b 	bl	0x47f0a558
47f352e8:	e1a00004 	mov	r0, r4
47f352ec:	ebffff62 	bl	0x47f3507c
47f352f0:	e1a00005 	mov	r0, r5
47f352f4:	e1a01006 	mov	r1, r6
47f352f8:	ebfffe13 	bl	0x47f34b4c
47f352fc:	e599304c 	ldr	r3, [r9, #76]	@ 0x4c
47f35300:	e2433001 	sub	r3, r3, #1
47f35304:	e589304c 	str	r3, [r9, #76]	@ 0x4c
47f35308:	e1a00005 	mov	r0, r5
47f3530c:	e0851006 	add	r1, r5, r6
47f35310:	ebff2fcd 	bl	0x47f0124c
47f35314:	e1a00004 	mov	r0, r4
47f35318:	ebfffd91 	bl	0x47f34964
47f3531c:	e3500000 	cmp	r0, #0
47f35320:	aa000003 	bge	0x47f35334
47f35324:	e59f0020 	ldr	r0, [pc, #32]	@ 0x47f3534c
47f35328:	ebff548a 	bl	0x47f0a558
47f3532c:	e3e00001 	mvn	r0, #1
47f35330:	e8bd82f0 	pop	{r4, r5, r6, r7, r9, pc}
47f35334:	e3a00000 	mov	r0, #0
47f35338:	e8bd82f0 	pop	{r4, r5, r6, r7, r9, pc}
47f3533c:	47f4466c 	ldrbmi	r4, [r4, r12, ror #12]!
47f35340:	47f44956 	ubfxmi	r4, r6, #18, #21
47f35344:	47f6235c 	ubfxmi	r2, r12, #6, #23
47f35348:	47f44699 			@ <UNDEFINED> instruction: 0x47f44699
47f3534c:	47f446b6 			@ <UNDEFINED> instruction: 0x47f446b6
47f35350:	e92d40f8 	push	{r3, r4, r5, r6, r7, lr}
47f35354:	e1a05002 	mov	r5, r2
47f35358:	e59f316c 	ldr	r3, [pc, #364]	@ 0x47f354cc
47f3535c:	e1a06001 	mov	r6, r1
47f35360:	e5932000 	ldr	r2, [r3]
47f35364:	e59f4164 	ldr	r4, [pc, #356]	@ 0x47f354d0
47f35368:	e1520004 	cmp	r2, r4
47f3536c:	1a000019 	bne	0x47f353d8
47f35370:	e59f315c 	ldr	r3, [pc, #348]	@ 0x47f354d4
47f35374:	e5932000 	ldr	r2, [r3]
47f35378:	e1a07003 	mov	r7, r3
47f3537c:	e3520009 	cmp	r2, #9
47f35380:	9a000000 	bls	0x47f35388
47f35384:	ebfffdd7 	bl	0x47f34ae8
47f35388:	e5972000 	ldr	r2, [r7]
47f3538c:	e59f3140 	ldr	r3, [pc, #320]	@ 0x47f354d4
47f35390:	e3520b01 	cmp	r2, #1024	@ 0x400
47f35394:	259f113c 	ldrcs	r1, [pc, #316]	@ 0x47f354d8
47f35398:	25911068 	ldrcs	r1, [r1, #104]	@ 0x68
47f3539c:	2a00001d 	bcs	0x47f35418
47f353a0:	e5931050 	ldr	r1, [r3, #80]	@ 0x50
47f353a4:	e593205c 	ldr	r2, [r3, #92]	@ 0x5c
47f353a8:	e0822201 	add	r2, r2, r1, lsl #4
47f353ac:	e2811001 	add	r1, r1, #1
47f353b0:	e3510b01 	cmp	r1, #1024	@ 0x400
47f353b4:	e5831050 	str	r1, [r3, #80]	@ 0x50
47f353b8:	23a01000 	movcs	r1, #0
47f353bc:	25831050 	strcs	r1, [r3, #80]	@ 0x50
47f353c0:	e3520000 	cmp	r2, #0
47f353c4:	1a000025 	bne	0x47f35460
47f353c8:	e59f010c 	ldr	r0, [pc, #268]	@ 0x47f354dc
47f353cc:	ebff5461 	bl	0x47f0a558
47f353d0:	e3e00000 	mvn	r0, #0
47f353d4:	e8bd80f8 	pop	{r3, r4, r5, r6, r7, pc}
47f353d8:	e5932000 	ldr	r2, [r3]
47f353dc:	e59f30fc 	ldr	r3, [pc, #252]	@ 0x47f354e0
47f353e0:	e1520003 	cmp	r2, r3
47f353e4:	1a000036 	bne	0x47f354c4
47f353e8:	e59f30e4 	ldr	r3, [pc, #228]	@ 0x47f354d4
47f353ec:	e5932000 	ldr	r2, [r3]
47f353f0:	e1a07003 	mov	r7, r3
47f353f4:	e3520009 	cmp	r2, #9
47f353f8:	9a000000 	bls	0x47f35400
47f353fc:	ebfffdb9 	bl	0x47f34ae8
47f35400:	e5972000 	ldr	r2, [r7]
47f35404:	e59f30c8 	ldr	r3, [pc, #200]	@ 0x47f354d4
47f35408:	e3520b01 	cmp	r2, #1024	@ 0x400
47f3540c:	3a00000c 	bcc	0x47f35444
47f35410:	e59f10c0 	ldr	r1, [pc, #192]	@ 0x47f354d8
47f35414:	e5911058 	ldr	r1, [r1, #88]	@ 0x58
47f35418:	e371037f 	cmn	r1, #-67108863	@ 0xfc000001
47f3541c:	e6ff0071 	uxth	r0, r1
47f35420:	e0602002 	rsb	r2, r0, r2
47f35424:	e5832000 	str	r2, [r3]
47f35428:	85932054 	ldrhi	r2, [r3, #84]	@ 0x54
47f3542c:	95932058 	ldrls	r2, [r3, #88]	@ 0x58
47f35430:	82822001 	addhi	r2, r2, #1
47f35434:	92822001 	addls	r2, r2, #1
47f35438:	85832054 	strhi	r2, [r3, #84]	@ 0x54
47f3543c:	95832058 	strls	r2, [r3, #88]	@ 0x58
47f35440:	eaffffe0 	b	0x47f353c8
47f35444:	e593c050 	ldr	r12, [r3, #80]	@ 0x50
47f35448:	e5932060 	ldr	r2, [r3, #96]	@ 0x60
47f3544c:	e082220c 	add	r2, r2, r12, lsl #4
47f35450:	e28cc001 	add	r12, r12, #1
47f35454:	e35c0b01 	cmp	r12, #1024	@ 0x400
47f35458:	e583c050 	str	r12, [r3, #80]	@ 0x50
47f3545c:	eaffffd5 	b	0x47f353b8
47f35460:	e59f3064 	ldr	r3, [pc, #100]	@ 0x47f354cc
47f35464:	e5931000 	ldr	r1, [r3]
47f35468:	e1510004 	cmp	r1, r4
47f3546c:	1a000008 	bne	0x47f35494
47f35470:	e3a00080 	mov	r0, #128	@ 0x80
47f35474:	e3a01902 	mov	r1, #32768	@ 0x8000
47f35478:	e3a03401 	mov	r3, #16777216	@ 0x1000000
47f3547c:	e3a0e002 	mov	lr, #2
47f35480:	e882400b 	stm	r2, {r0, r1, r3, lr}
47f35484:	e1a00006 	mov	r0, r6
47f35488:	e1a01005 	mov	r1, r5
47f3548c:	ebffff1c 	bl	0x47f35104
47f35490:	ea00000b 	b	0x47f354c4
47f35494:	e5931000 	ldr	r1, [r3]
47f35498:	e59f3040 	ldr	r3, [pc, #64]	@ 0x47f354e0
47f3549c:	e1510003 	cmp	r1, r3
47f354a0:	1a000007 	bne	0x47f354c4
47f354a4:	e59f0038 	ldr	r0, [pc, #56]	@ 0x47f354e4
47f354a8:	e3a01801 	mov	r1, #65536	@ 0x10000
47f354ac:	e3a03602 	mov	r3, #2097152	@ 0x200000
47f354b0:	e3a0c002 	mov	r12, #2
47f354b4:	e882100b 	stm	r2, {r0, r1, r3, r12}
47f354b8:	e1a00006 	mov	r0, r6
47f354bc:	e1a01005 	mov	r1, r5
47f354c0:	ebffff58 	bl	0x47f35228
47f354c4:	e3a00000 	mov	r0, #0
47f354c8:	e8bd80f8 	pop	{r3, r4, r5, r6, r7, pc}
47f354cc:	92040000 	andls	r0, r4, #0
47f354d0:	27912810 			@ <UNDEFINED> instruction: 0x27912810
47f354d4:	47f6235c 	ubfxmi	r2, r12, #6, #23
47f354d8:	92350000 	eorsls	r0, r5, #0
47f354dc:	47f446ca 	ldrbmi	r4, [r4, r10, asr #13]!
47f354e0:	27912710 			@ <UNDEFINED> instruction: 0x27912710
47f354e4:	02000080 	andeq	r0, r0, #128	@ 0x80
47f354e8:	e59f309c 	ldr	r3, [pc, #156]	@ 0x47f3558c
47f354ec:	e5931000 	ldr	r1, [r3]
47f354f0:	e59f2098 	ldr	r2, [pc, #152]	@ 0x47f35590
47f354f4:	e1510002 	cmp	r1, r2
47f354f8:	1a00000f 	bne	0x47f3553c
47f354fc:	e59fc090 	ldr	r12, [pc, #144]	@ 0x47f35594
47f35500:	e3a03000 	mov	r3, #0
47f35504:	e1a00003 	mov	r0, r3
47f35508:	e2832b83 	add	r2, r3, #134144	@ 0x20c00
47f3550c:	e1a0100c 	mov	r1, r12
47f35510:	e2822c01 	add	r2, r2, #256	@ 0x100
47f35514:	e1a02682 	lsl	r2, r2, #13
47f35518:	e7a12003 	str	r2, [r1, r3]!
47f3551c:	e2833008 	add	r3, r3, #8
47f35520:	e5810004 	str	r0, [r1, #4]
47f35524:	e3530040 	cmp	r3, #64	@ 0x40
47f35528:	1afffff6 	bne	0x47f35508
47f3552c:	e59f2064 	ldr	r2, [pc, #100]	@ 0x47f35598
47f35530:	e59f3064 	ldr	r3, [pc, #100]	@ 0x47f3559c
47f35534:	e583205c 	str	r2, [r3, #92]	@ 0x5c
47f35538:	e12fff1e 	bx	lr
47f3553c:	e5932000 	ldr	r2, [r3]
47f35540:	e59f3058 	ldr	r3, [pc, #88]	@ 0x47f355a0
47f35544:	e1520003 	cmp	r2, r3
47f35548:	112fff1e 	bxne	lr
47f3554c:	e59fc040 	ldr	r12, [pc, #64]	@ 0x47f35594
47f35550:	e3a03000 	mov	r3, #0
47f35554:	e1a00003 	mov	r0, r3
47f35558:	e2832b83 	add	r2, r3, #134144	@ 0x20c00
47f3555c:	e1a0100c 	mov	r1, r12
47f35560:	e2822c01 	add	r2, r2, #256	@ 0x100
47f35564:	e1a02682 	lsl	r2, r2, #13
47f35568:	e7a12003 	str	r2, [r1, r3]!
47f3556c:	e2833008 	add	r3, r3, #8
47f35570:	e5810004 	str	r0, [r1, #4]
47f35574:	e3530040 	cmp	r3, #64	@ 0x40
47f35578:	1afffff6 	bne	0x47f35558
47f3557c:	e59f2020 	ldr	r2, [pc, #32]	@ 0x47f355a4
47f35580:	e59f3014 	ldr	r3, [pc, #20]	@ 0x47f3559c
47f35584:	e5832060 	str	r2, [r3, #96]	@ 0x60
47f35588:	e12fff1e 	bx	lr
47f3558c:	92040000 	andls	r0, r4, #0
47f35590:	27912810 			@ <UNDEFINED> instruction: 0x27912810
47f35594:	47f62368 	ldrbmi	r2, [r6, r8, ror #6]!
47f35598:	41c00000 	bicmi	r0, r0, r0
47f3559c:	47f6235c 	ubfxmi	r2, r12, #6, #23
47f355a0:	27912710 			@ <UNDEFINED> instruction: 0x27912710
47f355a4:	41b00000 	movsmi	r0, r0
47f355a8:	e92d4008 	push	{r3, lr}
47f355ac:	e3a00000 	mov	r0, #0
47f355b0:	e59f100c 	ldr	r1, [pc, #12]	@ 0x47f355c4
47f355b4:	ebfffb00 	bl	0x47f341bc
47f355b8:	ebffffca 	bl	0x47f354e8
47f355bc:	e3a00000 	mov	r0, #0
47f355c0:	e8bd8008 	pop	{r3, pc}
47f355c4:	47f51934 			@ <UNDEFINED> instruction: 0x47f51934
47f355c8:	e92d4038 	push	{r3, r4, r5, lr}
47f355cc:	e3a00040 	mov	r0, #64	@ 0x40
47f355d0:	ebff55b8 	bl	0x47f0acb8
47f355d4:	e2504000 	subs	r4, r0, #0
47f355d8:	1a000001 	bne	0x47f355e4
47f355dc:	e8bd4038 	pop	{r3, r4, r5, lr}
47f355e0:	eaff552a 	b	0x47f0aa90
47f355e4:	e3a02040 	mov	r2, #64	@ 0x40
47f355e8:	e3a01000 	mov	r1, #0
47f355ec:	ebffc41c 	bl	0x47f26664
47f355f0:	e59f3064 	ldr	r3, [pc, #100]	@ 0x47f3565c
47f355f4:	e2845010 	add	r5, r4, #16
47f355f8:	e59f1060 	ldr	r1, [pc, #96]	@ 0x47f35660
47f355fc:	e1a00004 	mov	r0, r4
47f35600:	e5843020 	str	r3, [r4, #32]
47f35604:	e59f3058 	ldr	r3, [pc, #88]	@ 0x47f35664
47f35608:	e584302c 	str	r3, [r4, #44]	@ 0x2c
47f3560c:	e59f3054 	ldr	r3, [pc, #84]	@ 0x47f35668
47f35610:	e5843024 	str	r3, [r4, #36]	@ 0x24
47f35614:	e59f3050 	ldr	r3, [pc, #80]	@ 0x47f3566c
47f35618:	e5843028 	str	r3, [r4, #40]	@ 0x28
47f3561c:	ebffc864 	bl	0x47f277b4
47f35620:	e59f0048 	ldr	r0, [pc, #72]	@ 0x47f35670
47f35624:	e1a01005 	mov	r1, r5
47f35628:	ebffddaf 	bl	0x47f2ccec
47f3562c:	e3500000 	cmp	r0, #0
47f35630:	1a000002 	bne	0x47f35640
47f35634:	e59f0038 	ldr	r0, [pc, #56]	@ 0x47f35674
47f35638:	ebff53ba 	bl	0x47f0a528
47f3563c:	ea000003 	b	0x47f35650
47f35640:	e59f0030 	ldr	r0, [pc, #48]	@ 0x47f35678
47f35644:	e1a01005 	mov	r1, r5
47f35648:	e3a02006 	mov	r2, #6
47f3564c:	ebffc424 	bl	0x47f266e4
47f35650:	e1a00004 	mov	r0, r4
47f35654:	e8bd4038 	pop	{r3, r4, r5, lr}
47f35658:	eaffde89 	b	0x47f2d084
47f3565c:	47f34ba8 	ldrbmi	r4, [r3, r8, lsr #23]!
47f35660:	47f446de 	ubfxmi	r4, lr, #13, #21
47f35664:	47f34bd8 	ubfxmi	r4, r8, #23, #20
47f35668:	47f35350 	ubfxmi	r5, r0, #6, #20
47f3566c:	47f34ce4 	ldrbmi	r4, [r3, r4, ror #25]!
47f35670:	47f3ae4d 	ldrbmi	r10, [r3, sp, asr #28]!
47f35674:	47f446e3 	ldrbmi	r4, [r4, r3, ror #13]!
47f35678:	47f51934 			@ <UNDEFINED> instruction: 0x47f51934
47f3567c:	e59f3008 	ldr	r3, [pc, #8]	@ 0x47f3568c
47f35680:	e3a00000 	mov	r0, #0
47f35684:	e5830004 	str	r0, [r3, #4]
47f35688:	e12fff1e 	bx	lr
47f3568c:	9234c000 	eorsls	r12, r4, #0
47f35690:	e59f3018 	ldr	r3, [pc, #24]	@ 0x47f356b0
47f35694:	e303209a 	movw	r2, #12442	@ 0x309a
47f35698:	e3a00000 	mov	r0, #0
47f3569c:	e5832080 	str	r2, [r3, #128]	@ 0x80
47f356a0:	e3a02001 	mov	r2, #1
47f356a4:	e5830088 	str	r0, [r3, #136]	@ 0x88
47f356a8:	e58320cc 	str	r2, [r3, #204]	@ 0xcc
47f356ac:	e12fff1e 	bx	lr
47f356b0:	9238c000 	eorsls	r12, r8, #0
47f356b4:	e3003a37 	movw	r3, #2615	@ 0xa37
47f356b8:	e0000093 	mul	r0, r3, r0
47f356bc:	e59f3004 	ldr	r3, [pc, #4]	@ 0x47f356c8
47f356c0:	e5830188 	str	r0, [r3, #392]	@ 0x188
47f356c4:	e12fff1e 	bx	lr
47f356c8:	92388000 	eorsls	r8, r8, #0
47f356cc:	e59f3054 	ldr	r3, [pc, #84]	@ 0x47f35728
47f356d0:	e3a0103f 	mov	r1, #63	@ 0x3f
47f356d4:	e59f2050 	ldr	r2, [pc, #80]	@ 0x47f3572c
47f356d8:	e3050555 	movw	r0, #21845	@ 0x5555
47f356dc:	e5832004 	str	r2, [r3, #4]
47f356e0:	e59f2048 	ldr	r2, [pc, #72]	@ 0x47f35730
47f356e4:	e5832340 	str	r2, [r3, #832]	@ 0x340
47f356e8:	e3a0203e 	mov	r2, #62	@ 0x3e
47f356ec:	e5832344 	str	r2, [r3, #836]	@ 0x344
47f356f0:	e5831380 	str	r1, [r3, #896]	@ 0x380
47f356f4:	e59f1038 	ldr	r1, [pc, #56]	@ 0x47f35734
47f356f8:	e583163c 	str	r1, [r3, #1596]	@ 0x63c
47f356fc:	e3a010ff 	mov	r1, #255	@ 0xff
47f35700:	e58311c0 	str	r1, [r3, #448]	@ 0x1c0
47f35704:	e58301c4 	str	r0, [r3, #452]	@ 0x1c4
47f35708:	e59f0028 	ldr	r0, [pc, #40]	@ 0x47f35738
47f3570c:	e5830188 	str	r0, [r3, #392]	@ 0x188
47f35710:	e3a00000 	mov	r0, #0
47f35714:	e58312c0 	str	r1, [r3, #704]	@ 0x2c0
47f35718:	e30f1fff 	movw	r1, #65535	@ 0xffff
47f3571c:	e5831300 	str	r1, [r3, #768]	@ 0x300
47f35720:	e5832304 	str	r2, [r3, #772]	@ 0x304
47f35724:	e12fff1e 	bx	lr
47f35728:	92388000 	eorsls	r8, r8, #0
47f3572c:	000200ff 	strdeq	r0, [r2], -pc	@ <UNPREDICTABLE>
47f35730:	ff5555ff 			@ <UNDEFINED> instruction: 0xff5555ff
47f35734:	aaaaaaaa 	bge	0x469e01e4
47f35738:	000bf874 	andeq	pc, r11, r4, ror r8	@ <UNPREDICTABLE>
47f3573c:	e92d4008 	push	{r3, lr}
47f35740:	eb000007 	bl	0x47f35764
47f35744:	ebffffe0 	bl	0x47f356cc
47f35748:	ebffffd0 	bl	0x47f35690
47f3574c:	e59f300c 	ldr	r3, [pc, #12]	@ 0x47f35760
47f35750:	e3a00000 	mov	r0, #0
47f35754:	e5830010 	str	r0, [r3, #16]
47f35758:	e5830014 	str	r0, [r3, #20]
47f3575c:	e8bd8008 	pop	{r3, pc}
47f35760:	923a0000 	eorsls	r0, r10, #0
47f35764:	e92d4008 	push	{r3, lr}
47f35768:	e3a02002 	mov	r2, #2
47f3576c:	e59f3010 	ldr	r3, [pc, #16]	@ 0x47f35784
47f35770:	e3a00ffa 	mov	r0, #1000	@ 0x3e8
47f35774:	e5832000 	str	r2, [r3]
47f35778:	ebffc45d 	bl	0x47f268f4
47f3577c:	e3a00000 	mov	r0, #0
47f35780:	e8bd8008 	pop	{r3, pc}
47f35784:	92380000 	eorsls	r0, r8, #0
47f35788:	e3500007 	cmp	r0, #7
47f3578c:	812fff1e 	bxhi	lr
47f35790:	e59f3014 	ldr	r3, [pc, #20]	@ 0x47f357ac
47f35794:	e7933100 	ldr	r3, [r3, r0, lsl #2]
47f35798:	e3530000 	cmp	r3, #0
47f3579c:	a7eb1051 	ubfxge	r1, r1, #0, #12
47f357a0:	a59f2008 	ldrge	r2, [pc, #8]	@ 0x47f357b0
47f357a4:	a7821103 	strge	r1, [r2, r3, lsl #2]
47f357a8:	e12fff1e 	bx	lr
47f357ac:	47f3a7f8 			@ <UNDEFINED> instruction: 0x47f3a7f8
47f357b0:	921d428c 	andsls	r4, sp, #140, 4	@ 0xc0000008
47f357b4:	e92d4010 	push	{r4, lr}
47f357b8:	e3a04000 	mov	r4, #0
47f357bc:	e6ef0074 	uxtb	r0, r4
47f357c0:	e3a01001 	mov	r1, #1
47f357c4:	e2844001 	add	r4, r4, #1
47f357c8:	ebffffee 	bl	0x47f35788
47f357cc:	e3540008 	cmp	r4, #8
47f357d0:	1afffff9 	bne	0x47f357bc
47f357d4:	e59f3058 	ldr	r3, [pc, #88]	@ 0x47f35834
47f357d8:	e3a00203 	mov	r0, #805306368	@ 0x30000000
47f357dc:	e59f1054 	ldr	r1, [pc, #84]	@ 0x47f35838
47f357e0:	e3a02b22 	mov	r2, #34816	@ 0x8800
47f357e4:	e5830000 	str	r0, [r3]
47f357e8:	e5832004 	str	r2, [r3, #4]
47f357ec:	e591c000 	ldr	r12, [r1]
47f357f0:	e59f2044 	ldr	r2, [pc, #68]	@ 0x47f3583c
47f357f4:	e15c0002 	cmp	r12, r2
47f357f8:	0303cfff 	movweq	r12, #16383	@ 0x3fff
47f357fc:	0583c008 	streq	r12, [r3, #8]
47f35800:	e5830040 	str	r0, [r3, #64]	@ 0x40
47f35804:	e3a00b22 	mov	r0, #34816	@ 0x8800
47f35808:	e5830044 	str	r0, [r3, #68]	@ 0x44
47f3580c:	e5913000 	ldr	r3, [r1]
47f35810:	e1530002 	cmp	r3, r2
47f35814:	e3a00000 	mov	r0, #0
47f35818:	059f2020 	ldreq	r2, [pc, #32]	@ 0x47f35840
47f3581c:	059f3010 	ldreq	r3, [pc, #16]	@ 0x47f35834
47f35820:	05832048 	streq	r2, [r3, #72]	@ 0x48
47f35824:	e3a02411 	mov	r2, #285212672	@ 0x11000000
47f35828:	e59f3004 	ldr	r3, [pc, #4]	@ 0x47f35834
47f3582c:	e58321c0 	str	r2, [r3, #448]	@ 0x1c0
47f35830:	e8bd8010 	pop	{r4, pc}
47f35834:	921d4000 	andsls	r4, sp, #0
47f35838:	92040000 	andls	r0, r4, #0
47f3583c:	27912810 			@ <UNDEFINED> instruction: 0x27912810
47f35840:	0007ffff 	strdeq	pc, [r7], -pc	@ <UNPREDICTABLE>
47f35844:	e3500004 	cmp	r0, #4
47f35848:	812fff1e 	bxhi	lr
47f3584c:	e1a00900 	lsl	r0, r0, #18
47f35850:	e3510002 	cmp	r1, #2
47f35854:	e2800492 	add	r0, r0, #-1845493760	@ 0x92000000
47f35858:	e2800602 	add	r0, r0, #2097152	@ 0x200000
47f3585c:	e5903000 	ldr	r3, [r0]
47f35860:	03c33902 	biceq	r3, r3, #32768	@ 0x8000
47f35864:	03833a02 	orreq	r3, r3, #8192	@ 0x2000
47f35868:	0a000006 	beq	0x47f35888
47f3586c:	e3520000 	cmp	r2, #0
47f35870:	03c33a02 	biceq	r3, r3, #8192	@ 0x2000
47f35874:	13833a0a 	orrne	r3, r3, #40960	@ 0xa000
47f35878:	03833902 	orreq	r3, r3, #32768	@ 0x8000
47f3587c:	e3510001 	cmp	r1, #1
47f35880:	03833901 	orreq	r3, r3, #16384	@ 0x4000
47f35884:	13c33901 	bicne	r3, r3, #16384	@ 0x4000
47f35888:	e5803000 	str	r3, [r0]
47f3588c:	e12fff1e 	bx	lr
47f35890:	e3500004 	cmp	r0, #4
47f35894:	91a00900 	lslls	r0, r0, #18
47f35898:	92800492 	addls	r0, r0, #-1845493760	@ 0x92000000
47f3589c:	92800602 	addls	r0, r0, #2097152	@ 0x200000
47f358a0:	95903000 	ldrls	r3, [r0]
47f358a4:	93833003 	orrls	r3, r3, #3
47f358a8:	95803000 	strls	r3, [r0]
47f358ac:	e12fff1e 	bx	lr
47f358b0:	e3500004 	cmp	r0, #4
47f358b4:	e92d42f3 	push	{r0, r1, r4, r5, r6, r7, r9, lr}
47f358b8:	e3a05000 	mov	r5, #0
47f358bc:	e1cd50b4 	strh	r5, [sp, #4]
47f358c0:	e1cd50b6 	strh	r5, [sp, #6]
47f358c4:	8a00007f 	bhi	0x47f35ac8
47f358c8:	e59f6200 	ldr	r6, [pc, #512]	@ 0x47f35ad0
47f358cc:	e1a04000 	mov	r4, r0
47f358d0:	e3a0101e 	mov	r1, #30
47f358d4:	e28d2006 	add	r2, sp, #6
47f358d8:	e7d60000 	ldrb	r0, [r6, r0]
47f358dc:	ebffa975 	bl	0x47f1feb8
47f358e0:	e3a0101e 	mov	r1, #30
47f358e4:	e1a02005 	mov	r2, r5
47f358e8:	e7d60004 	ldrb	r0, [r6, r4]
47f358ec:	ebffa9ad 	bl	0x47f1ffa8
47f358f0:	e3a0101a 	mov	r1, #26
47f358f4:	e28d2004 	add	r2, sp, #4
47f358f8:	e7d60004 	ldrb	r0, [r6, r4]
47f358fc:	ebffa96d 	bl	0x47f1feb8
47f35900:	e3a0000a 	mov	r0, #10
47f35904:	ebffc406 	bl	0x47f26924
47f35908:	e3a0101a 	mov	r1, #26
47f3590c:	e28d2004 	add	r2, sp, #4
47f35910:	e7d60004 	ldrb	r0, [r6, r4]
47f35914:	ebffa967 	bl	0x47f1feb8
47f35918:	e7d60004 	ldrb	r0, [r6, r4]
47f3591c:	e3a0101e 	mov	r1, #30
47f35920:	e1dd20b6 	ldrh	r2, [sp, #6]
47f35924:	ebffa99f 	bl	0x47f1ffa8
47f35928:	e1dd30b4 	ldrh	r3, [sp, #4]
47f3592c:	e3130040 	tst	r3, #64	@ 0x40
47f35930:	0a000064 	beq	0x47f35ac8
47f35934:	e59f6198 	ldr	r6, [pc, #408]	@ 0x47f35ad4
47f35938:	e2033d0e 	and	r3, r3, #896	@ 0x380
47f3593c:	e1cd30b4 	strh	r3, [sp, #4]
47f35940:	e7962104 	ldr	r2, [r6, r4, lsl #2]
47f35944:	e1530002 	cmp	r3, r2
47f35948:	1a000002 	bne	0x47f35958
47f3594c:	e1a00004 	mov	r0, r4
47f35950:	ebffffce 	bl	0x47f35890
47f35954:	ea00005b 	b	0x47f35ac8
47f35958:	e1a033a3 	lsr	r3, r3, #7
47f3595c:	e3530001 	cmp	r3, #1
47f35960:	9a000007 	bls	0x47f35984
47f35964:	e2432002 	sub	r2, r3, #2
47f35968:	e3520001 	cmp	r2, #1
47f3596c:	93a05001 	movls	r5, #1
47f35970:	9a000003 	bls	0x47f35984
47f35974:	e2432004 	sub	r2, r3, #4
47f35978:	e3520001 	cmp	r2, #1
47f3597c:	83a05000 	movhi	r5, #0
47f35980:	93a05002 	movls	r5, #2
47f35984:	e2137005 	ands	r7, r3, #5
47f35988:	03a02001 	moveq	r2, #1
47f3598c:	13a02000 	movne	r2, #0
47f35990:	e3530004 	cmp	r3, #4
47f35994:	03822001 	orreq	r2, r2, #1
47f35998:	e3520000 	cmp	r2, #0
47f3599c:	13a07000 	movne	r7, #0
47f359a0:	1a000003 	bne	0x47f359b4
47f359a4:	e3530005 	cmp	r3, #5
47f359a8:	13570001 	cmpne	r7, #1
47f359ac:	03a07001 	moveq	r7, #1
47f359b0:	13a07000 	movne	r7, #0
47f359b4:	e59f211c 	ldr	r2, [pc, #284]	@ 0x47f35ad8
47f359b8:	e1a01004 	mov	r1, r4
47f359bc:	e59f0118 	ldr	r0, [pc, #280]	@ 0x47f35adc
47f359c0:	e3a09001 	mov	r9, #1
47f359c4:	e2823020 	add	r3, r2, #32
47f359c8:	e0822185 	add	r2, r2, r5, lsl #3
47f359cc:	e0833207 	add	r3, r3, r7, lsl #4
47f359d0:	ebff52e0 	bl	0x47f0a558
47f359d4:	e2840006 	add	r0, r4, #6
47f359d8:	e1a00019 	lsl	r0, r9, r0
47f359dc:	ebfffa20 	bl	0x47f34264
47f359e0:	e1a01904 	lsl	r1, r4, #18
47f359e4:	e2813492 	add	r3, r1, #-1845493760	@ 0x92000000
47f359e8:	e59f20f0 	ldr	r2, [pc, #240]	@ 0x47f35ae0
47f359ec:	e2833602 	add	r3, r3, #2097152	@ 0x200000
47f359f0:	e59f00ec 	ldr	r0, [pc, #236]	@ 0x47f35ae4
47f359f4:	e5832000 	str	r2, [r3]
47f359f8:	e2813289 	add	r3, r1, #-1879048184	@ 0x90000008
47f359fc:	e2833622 	add	r3, r3, #35651584	@ 0x2200000
47f35a00:	e3a02106 	mov	r2, #-2147483647	@ 0x80000001
47f35a04:	e2811249 	add	r1, r1, #-1879048188	@ 0x90000004
47f35a08:	e5832000 	str	r2, [r3]
47f35a0c:	e2811622 	add	r1, r1, #35651584	@ 0x2200000
47f35a10:	e59f20d0 	ldr	r2, [pc, #208]	@ 0x47f35ae8
47f35a14:	e59f30d0 	ldr	r3, [pc, #208]	@ 0x47f35aec
47f35a18:	e7832904 	str	r2, [r3, r4, lsl #18]
47f35a1c:	e2833ec2 	add	r3, r3, #3104	@ 0xc20
47f35a20:	e3a02032 	mov	r2, #50	@ 0x32
47f35a24:	e7832904 	str	r2, [r3, r4, lsl #18]
47f35a28:	e2833030 	add	r3, r3, #48	@ 0x30
47f35a2c:	e3a020a8 	mov	r2, #168	@ 0xa8
47f35a30:	e7832904 	str	r2, [r3, r4, lsl #18]
47f35a34:	e30f3ffe 	movw	r3, #65534	@ 0xfffe
47f35a38:	e59f20b0 	ldr	r2, [pc, #176]	@ 0x47f35af0
47f35a3c:	e5813000 	str	r3, [r1]
47f35a40:	e59f30ac 	ldr	r3, [pc, #172]	@ 0x47f35af4
47f35a44:	e7832904 	str	r2, [r3, r4, lsl #18]
47f35a48:	e2833044 	add	r3, r3, #68	@ 0x44
47f35a4c:	e3a02901 	mov	r2, #16384	@ 0x4000
47f35a50:	e7832904 	str	r2, [r3, r4, lsl #18]
47f35a54:	e2833d29 	add	r3, r3, #2624	@ 0xa40
47f35a58:	e59f2098 	ldr	r2, [pc, #152]	@ 0x47f35af8
47f35a5c:	e283300c 	add	r3, r3, #12
47f35a60:	e7832904 	str	r2, [r3, r4, lsl #18]
47f35a64:	ebff52bb 	bl	0x47f0a558
47f35a68:	e1a01005 	mov	r1, r5
47f35a6c:	e1a02007 	mov	r2, r7
47f35a70:	e1a00004 	mov	r0, r4
47f35a74:	ebffff72 	bl	0x47f35844
47f35a78:	e59f707c 	ldr	r7, [pc, #124]	@ 0x47f35afc
47f35a7c:	e2843005 	add	r3, r4, #5
47f35a80:	e3a05005 	mov	r5, #5
47f35a84:	e1a09319 	lsl	r9, r9, r3
47f35a88:	e3a00001 	mov	r0, #1
47f35a8c:	ebffc3a4 	bl	0x47f26924
47f35a90:	e5973068 	ldr	r3, [r7, #104]	@ 0x68
47f35a94:	e1190003 	tst	r9, r3
47f35a98:	1a000002 	bne	0x47f35aa8
47f35a9c:	e2555001 	subs	r5, r5, #1
47f35aa0:	1afffff8 	bne	0x47f35a88
47f35aa4:	ea000003 	b	0x47f35ab8
47f35aa8:	e3a02001 	mov	r2, #1
47f35aac:	e1833412 	orr	r3, r3, r2, lsl r4
47f35ab0:	e59f2044 	ldr	r2, [pc, #68]	@ 0x47f35afc
47f35ab4:	e5823068 	str	r3, [r2, #104]	@ 0x68
47f35ab8:	e1a00004 	mov	r0, r4
47f35abc:	ebffff73 	bl	0x47f35890
47f35ac0:	e1dd30b4 	ldrh	r3, [sp, #4]
47f35ac4:	e7863104 	str	r3, [r6, r4, lsl #2]
47f35ac8:	e28dd008 	add	sp, sp, #8
47f35acc:	e8bd82f0 	pop	{r4, r5, r6, r7, r9, pc}
47f35ad0:	47f51940 	ldrbmi	r1, [r5, r0, asr #18]!
47f35ad4:	47f623c0 	ldrbmi	r2, [r6, r0, asr #7]!
47f35ad8:	47f51945 	ldrbmi	r1, [r5, r5, asr #18]!
47f35adc:	47f44718 			@ <UNDEFINED> instruction: 0x47f44718
47f35ae0:	00bbe003 	adcseq	lr, r11, r3
47f35ae4:	47f4473a 			@ <UNDEFINED> instruction: 0x47f4473a
47f35ae8:	00011200 	andeq	r1, r1, r0, lsl #4
47f35aec:	922000e0 	eorls	r0, r0, #224	@ 0xe0
47f35af0:	00300002 	eorseq	r0, r0, r2
47f35af4:	92200070 	eorls	r0, r0, #112	@ 0x70
47f35af8:	0010ff11 	andseq	pc, r0, r1, lsl pc	@ <UNPREDICTABLE>
47f35afc:	921d9000 	andsls	r9, sp, #0
47f35b00:	e3500004 	cmp	r0, #4
47f35b04:	91a00900 	lslls	r0, r0, #18
47f35b08:	92800492 	addls	r0, r0, #-1845493760	@ 0x92000000
47f35b0c:	92800602 	addls	r0, r0, #2097152	@ 0x200000
47f35b10:	95903000 	ldrls	r3, [r0]
47f35b14:	93c33001 	bicls	r3, r3, #1
47f35b18:	95803000 	strls	r3, [r0]
47f35b1c:	e12fff1e 	bx	lr
47f35b20:	e59f3018 	ldr	r3, [pc, #24]	@ 0x47f35b40
47f35b24:	e0803003 	add	r3, r0, r3
47f35b28:	e1a03103 	lsl	r3, r3, #2
47f35b2c:	e5932000 	ldr	r2, [r3]
47f35b30:	e3c2250e 	bic	r2, r2, #58720256	@ 0x3800000
47f35b34:	e1821001 	orr	r1, r2, r1
47f35b38:	e5831000 	str	r1, [r3]
47f35b3c:	e12fff1e 	bx	lr
47f35b40:	24870018 	strcs	r0, [r7], #24
47f35b44:	e92d4070 	push	{r4, r5, r6, lr}
47f35b48:	e3a04000 	mov	r4, #0
47f35b4c:	e59f5024 	ldr	r5, [pc, #36]	@ 0x47f35b78
47f35b50:	e3e06000 	mvn	r6, #0
47f35b54:	e7856104 	str	r6, [r5, r4, lsl #2]
47f35b58:	e1a00004 	mov	r0, r4
47f35b5c:	e3a01000 	mov	r1, #0
47f35b60:	e2844001 	add	r4, r4, #1
47f35b64:	ebffffed 	bl	0x47f35b20
47f35b68:	e3540004 	cmp	r4, #4
47f35b6c:	1afffff8 	bne	0x47f35b54
47f35b70:	e3a00000 	mov	r0, #0
47f35b74:	e8bd8070 	pop	{r4, r5, r6, pc}
47f35b78:	47f623c0 	ldrbmi	r2, [r6, r0, asr #7]!
47f35b7c:	e59f3008 	ldr	r3, [pc, #8]	@ 0x47f35b8c
47f35b80:	e3a02011 	mov	r2, #17
47f35b84:	e5832000 	str	r2, [r3]
47f35b88:	e12fff1e 	bx	lr
47f35b8c:	921cc000 	andsls	r12, r12, #0
47f35b90:	e92d4038 	push	{r3, r4, r5, lr}
47f35b94:	e3a00ffa 	mov	r0, #1000	@ 0x3e8
47f35b98:	e59f402c 	ldr	r4, [pc, #44]	@ 0x47f35bcc
47f35b9c:	e3e05000 	mvn	r5, #0
47f35ba0:	e5845008 	str	r5, [r4, #8]
47f35ba4:	ebffc352 	bl	0x47f268f4
47f35ba8:	e584500c 	str	r5, [r4, #12]
47f35bac:	e3a00ffa 	mov	r0, #1000	@ 0x3e8
47f35bb0:	ebffc34f 	bl	0x47f268f4
47f35bb4:	ebfffefe 	bl	0x47f357b4
47f35bb8:	ebffffe1 	bl	0x47f35b44
47f35bbc:	ebffffee 	bl	0x47f35b7c
47f35bc0:	e3a00000 	mov	r0, #0
47f35bc4:	e5840048 	str	r0, [r4, #72]	@ 0x48
47f35bc8:	e8bd8038 	pop	{r3, r4, r5, pc}
47f35bcc:	921c0000 	andsls	r0, r12, #0
47f35bd0:	e1a01000 	mov	r1, r0
47f35bd4:	e59f000c 	ldr	r0, [pc, #12]	@ 0x47f35be8
47f35bd8:	e92d4008 	push	{r3, lr}
47f35bdc:	ebff525d 	bl	0x47f0a558
47f35be0:	e3a00000 	mov	r0, #0
47f35be4:	e8bd8008 	pop	{r3, pc}
47f35be8:	47f44968 	ldrbmi	r4, [r4, r8, ror #18]!
47f35bec:	e12fff1e 	bx	lr
47f35bf0:	e12fff1e 	bx	lr
47f35bf4:	e2512001 	subs	r2, r1, #1
47f35bf8:	012fff1e 	bxeq	lr
47f35bfc:	3a000023 	bcc	0x47f35c90
47f35c00:	e1500001 	cmp	r0, r1
47f35c04:	9a00001a 	bls	0x47f35c74
47f35c08:	e1110002 	tst	r1, r2
47f35c0c:	0a00001b 	beq	0x47f35c80
47f35c10:	e16f3f11 	clz	r3, r1
47f35c14:	e16f2f10 	clz	r2, r0
47f35c18:	e0432002 	sub	r2, r3, r2
47f35c1c:	e3a03001 	mov	r3, #1
47f35c20:	e1a01211 	lsl	r1, r1, r2
47f35c24:	e1a03213 	lsl	r3, r3, r2
47f35c28:	e3a02000 	mov	r2, #0
47f35c2c:	e1500001 	cmp	r0, r1
47f35c30:	20400001 	subcs	r0, r0, r1
47f35c34:	21822003 	orrcs	r2, r2, r3
47f35c38:	e15000a1 	cmp	r0, r1, lsr #1
47f35c3c:	204000a1 	subcs	r0, r0, r1, lsr #1
47f35c40:	218220a3 	orrcs	r2, r2, r3, lsr #1
47f35c44:	e1500121 	cmp	r0, r1, lsr #2
47f35c48:	20400121 	subcs	r0, r0, r1, lsr #2
47f35c4c:	21822123 	orrcs	r2, r2, r3, lsr #2
47f35c50:	e15001a1 	cmp	r0, r1, lsr #3
47f35c54:	204001a1 	subcs	r0, r0, r1, lsr #3
47f35c58:	218221a3 	orrcs	r2, r2, r3, lsr #3
47f35c5c:	e3500000 	cmp	r0, #0
47f35c60:	11b03223 	lsrsne	r3, r3, #4
47f35c64:	11a01221 	lsrne	r1, r1, #4
47f35c68:	1affffef 	bne	0x47f35c2c
47f35c6c:	e1a00002 	mov	r0, r2
47f35c70:	e12fff1e 	bx	lr
47f35c74:	03a00001 	moveq	r0, #1
47f35c78:	13a00000 	movne	r0, #0
47f35c7c:	e12fff1e 	bx	lr
47f35c80:	e16f2f11 	clz	r2, r1
47f35c84:	e262201f 	rsb	r2, r2, #31
47f35c88:	e1a00230 	lsr	r0, r0, r2
47f35c8c:	e12fff1e 	bx	lr
47f35c90:	e3500000 	cmp	r0, #0
47f35c94:	13e00000 	mvnne	r0, #0
47f35c98:	ea00006a 	b	0x47f35e48
47f35c9c:	e3510000 	cmp	r1, #0
47f35ca0:	0afffffa 	beq	0x47f35c90
47f35ca4:	e92d4003 	push	{r0, r1, lr}
47f35ca8:	ebffffd1 	bl	0x47f35bf4
47f35cac:	e8bd4006 	pop	{r1, r2, lr}
47f35cb0:	e0030092 	mul	r3, r2, r0
47f35cb4:	e0411003 	sub	r1, r1, r3
47f35cb8:	e12fff1e 	bx	lr
47f35cbc:	e3510000 	cmp	r1, #0
47f35cc0:	0a000030 	beq	0x47f35d88
47f35cc4:	e020c001 	eor	r12, r0, r1
47f35cc8:	42611000 	rsbmi	r1, r1, #0
47f35ccc:	e2512001 	subs	r2, r1, #1
47f35cd0:	0a00001f 	beq	0x47f35d54
47f35cd4:	e1b03000 	movs	r3, r0
47f35cd8:	42603000 	rsbmi	r3, r0, #0
47f35cdc:	e1530001 	cmp	r3, r1
47f35ce0:	9a00001e 	bls	0x47f35d60
47f35ce4:	e1110002 	tst	r1, r2
47f35ce8:	0a000020 	beq	0x47f35d70
47f35cec:	e16f2f11 	clz	r2, r1
47f35cf0:	e16f0f13 	clz	r0, r3
47f35cf4:	e0420000 	sub	r0, r2, r0
47f35cf8:	e3a02001 	mov	r2, #1
47f35cfc:	e1a01011 	lsl	r1, r1, r0
47f35d00:	e1a02012 	lsl	r2, r2, r0
47f35d04:	e3a00000 	mov	r0, #0
47f35d08:	e1530001 	cmp	r3, r1
47f35d0c:	20433001 	subcs	r3, r3, r1
47f35d10:	21800002 	orrcs	r0, r0, r2
47f35d14:	e15300a1 	cmp	r3, r1, lsr #1
47f35d18:	204330a1 	subcs	r3, r3, r1, lsr #1
47f35d1c:	218000a2 	orrcs	r0, r0, r2, lsr #1
47f35d20:	e1530121 	cmp	r3, r1, lsr #2
47f35d24:	20433121 	subcs	r3, r3, r1, lsr #2
47f35d28:	21800122 	orrcs	r0, r0, r2, lsr #2
47f35d2c:	e15301a1 	cmp	r3, r1, lsr #3
47f35d30:	204331a1 	subcs	r3, r3, r1, lsr #3
47f35d34:	218001a2 	orrcs	r0, r0, r2, lsr #3
47f35d38:	e3530000 	cmp	r3, #0
47f35d3c:	11b02222 	lsrsne	r2, r2, #4
47f35d40:	11a01221 	lsrne	r1, r1, #4
47f35d44:	1affffef 	bne	0x47f35d08
47f35d48:	e35c0000 	cmp	r12, #0
47f35d4c:	42600000 	rsbmi	r0, r0, #0
47f35d50:	e12fff1e 	bx	lr
47f35d54:	e13c0000 	teq	r12, r0
47f35d58:	42600000 	rsbmi	r0, r0, #0
47f35d5c:	e12fff1e 	bx	lr
47f35d60:	33a00000 	movcc	r0, #0
47f35d64:	01a00fcc 	asreq	r0, r12, #31
47f35d68:	03800001 	orreq	r0, r0, #1
47f35d6c:	e12fff1e 	bx	lr
47f35d70:	e16f2f11 	clz	r2, r1
47f35d74:	e262201f 	rsb	r2, r2, #31
47f35d78:	e35c0000 	cmp	r12, #0
47f35d7c:	e1a00233 	lsr	r0, r3, r2
47f35d80:	42600000 	rsbmi	r0, r0, #0
47f35d84:	e12fff1e 	bx	lr
47f35d88:	e3500000 	cmp	r0, #0
47f35d8c:	c3e00102 	mvngt	r0, #-2147483648	@ 0x80000000
47f35d90:	b3a00102 	movlt	r0, #-2147483648	@ 0x80000000
47f35d94:	ea00002b 	b	0x47f35e48
47f35d98:	e3510000 	cmp	r1, #0
47f35d9c:	0afffff9 	beq	0x47f35d88
47f35da0:	e92d4003 	push	{r0, r1, lr}
47f35da4:	ebffffc6 	bl	0x47f35cc4
47f35da8:	e8bd4006 	pop	{r1, r2, lr}
47f35dac:	e0030092 	mul	r3, r2, r0
47f35db0:	e0411003 	sub	r1, r1, r3
47f35db4:	e12fff1e 	bx	lr
47f35db8:	e2523020 	subs	r3, r2, #32
47f35dbc:	e262c020 	rsb	r12, r2, #32
47f35dc0:	41a00230 	lsrmi	r0, r0, r2
47f35dc4:	51a00331 	lsrpl	r0, r1, r3
47f35dc8:	41800c11 	orrmi	r0, r0, r1, lsl r12
47f35dcc:	e1a01231 	lsr	r1, r1, r2
47f35dd0:	e12fff1e 	bx	lr
47f35dd4:	e2523020 	subs	r3, r2, #32
47f35dd8:	e262c020 	rsb	r12, r2, #32
47f35ddc:	41a00230 	lsrmi	r0, r0, r2
47f35de0:	51a00351 	asrpl	r0, r1, r3
47f35de4:	41800c11 	orrmi	r0, r0, r1, lsl r12
47f35de8:	e1a01251 	asr	r1, r1, r2
47f35dec:	e12fff1e 	bx	lr
47f35df0:	e2523020 	subs	r3, r2, #32
47f35df4:	e262c020 	rsb	r12, r2, #32
47f35df8:	41a01211 	lslmi	r1, r1, r2
47f35dfc:	51a01310 	lslpl	r1, r0, r3
47f35e00:	41811c30 	orrmi	r1, r1, r0, lsr r12
47f35e04:	e1a00210 	lsl	r0, r0, r2
47f35e08:	e12fff1e 	bx	lr
47f35e0c:	e3530000 	cmp	r3, #0
47f35e10:	03520000 	cmpeq	r2, #0
47f35e14:	1a000004 	bne	0x47f35e2c
47f35e18:	e3510000 	cmp	r1, #0
47f35e1c:	03500000 	cmpeq	r0, #0
47f35e20:	13e01000 	mvnne	r1, #0
47f35e24:	13e00000 	mvnne	r0, #0
47f35e28:	ea000006 	b	0x47f35e48
47f35e2c:	e24dd008 	sub	sp, sp, #8
47f35e30:	e92d6000 	push	{sp, lr}
47f35e34:	eb000016 	bl	0x47f35e94
47f35e38:	e59de004 	ldr	lr, [sp, #4]
47f35e3c:	e28dd008 	add	sp, sp, #8
47f35e40:	e8bd000c 	pop	{r2, r3}
47f35e44:	e12fff1e 	bx	lr
47f35e48:	e92d4002 	push	{r1, lr}
47f35e4c:	e3a00008 	mov	r0, #8
47f35e50:	ebffff5e 	bl	0x47f35bd0
47f35e54:	e8bd8002 	pop	{r1, pc}
47f35e58:	e92d40f8 	push	{r3, r4, r5, r6, r7, lr}
47f35e5c:	e1a04002 	mov	r4, r2
47f35e60:	e1a06000 	mov	r6, r0
47f35e64:	e1a07001 	mov	r7, r1
47f35e68:	e1a05003 	mov	r5, r3
47f35e6c:	eb000017 	bl	0x47f35ed0
47f35e70:	e0030194 	mul	r3, r4, r1
47f35e74:	e59dc018 	ldr	r12, [sp, #24]
47f35e78:	e0253590 	mla	r5, r0, r5, r3
47f35e7c:	e0832094 	umull	r2, r3, r4, r0
47f35e80:	e0562002 	subs	r2, r6, r2
47f35e84:	e0853003 	add	r3, r5, r3
47f35e88:	e0c73003 	sbc	r3, r7, r3
47f35e8c:	e1cc20f0 	strd	r2, [r12]
47f35e90:	e8bd80f8 	pop	{r3, r4, r5, r6, r7, pc}
47f35e94:	e92d40f8 	push	{r3, r4, r5, r6, r7, lr}
47f35e98:	e1a06003 	mov	r6, r3
47f35e9c:	e1a07002 	mov	r7, r2
47f35ea0:	e1a04000 	mov	r4, r0
47f35ea4:	e1a05001 	mov	r5, r1
47f35ea8:	eb00005f 	bl	0x47f3602c
47f35eac:	e0060690 	mul	r6, r0, r6
47f35eb0:	e59dc018 	ldr	r12, [sp, #24]
47f35eb4:	e0832790 	umull	r2, r3, r0, r7
47f35eb8:	e0266197 	mla	r6, r7, r1, r6
47f35ebc:	e0542002 	subs	r2, r4, r2
47f35ec0:	e0863003 	add	r3, r6, r3
47f35ec4:	e0c53003 	sbc	r3, r5, r3
47f35ec8:	e1cc20f0 	strd	r2, [r12]
47f35ecc:	e8bd80f8 	pop	{r3, r4, r5, r6, r7, pc}
47f35ed0:	e3510000 	cmp	r1, #0
47f35ed4:	e92d4ff8 	push	{r3, r4, r5, r6, r7, r8, r9, r10, r11, lr}
47f35ed8:	e1a0c003 	mov	r12, r3
47f35edc:	e1a0e002 	mov	lr, r2
47f35ee0:	a1a07000 	movge	r7, r0
47f35ee4:	a1a06001 	movge	r6, r1
47f35ee8:	a3a0a000 	movge	r10, #0
47f35eec:	aa000004 	bge	0x47f35f04
47f35ef0:	e2700000 	rsbs	r0, r0, #0
47f35ef4:	e3e0a000 	mvn	r10, #0
47f35ef8:	e2e11000 	rsc	r1, r1, #0
47f35efc:	e1a07000 	mov	r7, r0
47f35f00:	e1a06001 	mov	r6, r1
47f35f04:	e3530000 	cmp	r3, #0
47f35f08:	aa000004 	bge	0x47f35f20
47f35f0c:	e2722000 	rsbs	r2, r2, #0
47f35f10:	e1e0a00a 	mvn	r10, r10
47f35f14:	e2e33000 	rsc	r3, r3, #0
47f35f18:	e1a0e002 	mov	lr, r2
47f35f1c:	e1a0c003 	mov	r12, r3
47f35f20:	e15c0006 	cmp	r12, r6
47f35f24:	e1a0000e 	mov	r0, lr
47f35f28:	015e0007 	cmpeq	lr, r7
47f35f2c:	e1a0100c 	mov	r1, r12
47f35f30:	e1a04007 	mov	r4, r7
47f35f34:	e1a05006 	mov	r5, r6
47f35f38:	83a00000 	movhi	r0, #0
47f35f3c:	83a01000 	movhi	r1, #0
47f35f40:	8a000034 	bhi	0x47f36018
47f35f44:	e3510000 	cmp	r1, #0
47f35f48:	016f7f10 	clzeq	r7, r0
47f35f4c:	116f7f11 	clzne	r7, r1
47f35f50:	02877020 	addeq	r7, r7, #32
47f35f54:	e3560000 	cmp	r6, #0
47f35f58:	016f3f14 	clzeq	r3, r4
47f35f5c:	02833020 	addeq	r3, r3, #32
47f35f60:	116f3f16 	clzne	r3, r6
47f35f64:	e0637007 	rsb	r7, r3, r7
47f35f68:	e1a02007 	mov	r2, r7
47f35f6c:	e1a0b007 	mov	r11, r7
47f35f70:	ebffff9e 	bl	0x47f35df0
47f35f74:	e1560001 	cmp	r6, r1
47f35f78:	e1a08000 	mov	r8, r0
47f35f7c:	01540000 	cmpeq	r4, r0
47f35f80:	e1a09001 	mov	r9, r1
47f35f84:	33a00000 	movcc	r0, #0
47f35f88:	33a01000 	movcc	r1, #0
47f35f8c:	3a000005 	bcc	0x47f35fa8
47f35f90:	e0544008 	subs	r4, r4, r8
47f35f94:	e3a00001 	mov	r0, #1
47f35f98:	e3a01000 	mov	r1, #0
47f35f9c:	e1a02007 	mov	r2, r7
47f35fa0:	e0c65009 	sbc	r5, r6, r9
47f35fa4:	ebffff91 	bl	0x47f35df0
47f35fa8:	e3570000 	cmp	r7, #0
47f35fac:	0a000019 	beq	0x47f36018
47f35fb0:	e1b090a9 	lsrs	r9, r9, #1
47f35fb4:	e1a08068 	rrx	r8, r8
47f35fb8:	e1550009 	cmp	r5, r9
47f35fbc:	01540008 	cmpeq	r4, r8
47f35fc0:	3a000006 	bcc	0x47f35fe0
47f35fc4:	e0544008 	subs	r4, r4, r8
47f35fc8:	e0c55009 	sbc	r5, r5, r9
47f35fcc:	e0944004 	adds	r4, r4, r4
47f35fd0:	e0a55005 	adc	r5, r5, r5
47f35fd4:	e2944001 	adds	r4, r4, #1
47f35fd8:	e2a55000 	adc	r5, r5, #0
47f35fdc:	ea000001 	b	0x47f35fe8
47f35fe0:	e0944004 	adds	r4, r4, r4
47f35fe4:	e0a55005 	adc	r5, r5, r5
47f35fe8:	e2577001 	subs	r7, r7, #1
47f35fec:	1afffff1 	bne	0x47f35fb8
47f35ff0:	e0946000 	adds	r6, r4, r0
47f35ff4:	e1a0200b 	mov	r2, r11
47f35ff8:	e0a57001 	adc	r7, r5, r1
47f35ffc:	e1a00004 	mov	r0, r4
47f36000:	e1a01005 	mov	r1, r5
47f36004:	ebffff6b 	bl	0x47f35db8
47f36008:	e1a0200b 	mov	r2, r11
47f3600c:	ebffff77 	bl	0x47f35df0
47f36010:	e0560000 	subs	r0, r6, r0
47f36014:	e0c71001 	sbc	r1, r7, r1
47f36018:	e35a0000 	cmp	r10, #0
47f3601c:	08bd8ff8 	popeq	{r3, r4, r5, r6, r7, r8, r9, r10, r11, pc}
47f36020:	e2700000 	rsbs	r0, r0, #0
47f36024:	e2e11000 	rsc	r1, r1, #0
47f36028:	e8bd8ff8 	pop	{r3, r4, r5, r6, r7, r8, r9, r10, r11, pc}
47f3602c:	e1530001 	cmp	r3, r1
47f36030:	e92d43f8 	push	{r3, r4, r5, r6, r7, r8, r9, lr}
47f36034:	01520000 	cmpeq	r2, r0
47f36038:	e1a04000 	mov	r4, r0
47f3603c:	e1a05001 	mov	r5, r1
47f36040:	8a000037 	bhi	0x47f36124
47f36044:	e3530000 	cmp	r3, #0
47f36048:	016f6f12 	clzeq	r6, r2
47f3604c:	116f6f13 	clzne	r6, r3
47f36050:	02866020 	addeq	r6, r6, #32
47f36054:	e3510000 	cmp	r1, #0
47f36058:	016f1f10 	clzeq	r1, r0
47f3605c:	02811020 	addeq	r1, r1, #32
47f36060:	116f1f11 	clzne	r1, r1
47f36064:	e0616006 	rsb	r6, r1, r6
47f36068:	e1a00002 	mov	r0, r2
47f3606c:	e1a01003 	mov	r1, r3
47f36070:	e1a02006 	mov	r2, r6
47f36074:	ebffff5d 	bl	0x47f35df0
47f36078:	e1550001 	cmp	r5, r1
47f3607c:	e1a08000 	mov	r8, r0
47f36080:	01540000 	cmpeq	r4, r0
47f36084:	e1a09001 	mov	r9, r1
47f36088:	e1a07006 	mov	r7, r6
47f3608c:	33a00000 	movcc	r0, #0
47f36090:	33a01000 	movcc	r1, #0
47f36094:	3a000005 	bcc	0x47f360b0
47f36098:	e0544008 	subs	r4, r4, r8
47f3609c:	e3a00001 	mov	r0, #1
47f360a0:	e3a01000 	mov	r1, #0
47f360a4:	e1a02006 	mov	r2, r6
47f360a8:	e0c55009 	sbc	r5, r5, r9
47f360ac:	ebffff4f 	bl	0x47f35df0
47f360b0:	e3560000 	cmp	r6, #0
47f360b4:	08bd83f8 	popeq	{r3, r4, r5, r6, r7, r8, r9, pc}
47f360b8:	e1b090a9 	lsrs	r9, r9, #1
47f360bc:	e1a08068 	rrx	r8, r8
47f360c0:	e1550009 	cmp	r5, r9
47f360c4:	01540008 	cmpeq	r4, r8
47f360c8:	3a000006 	bcc	0x47f360e8
47f360cc:	e0544008 	subs	r4, r4, r8
47f360d0:	e0c55009 	sbc	r5, r5, r9
47f360d4:	e0944004 	adds	r4, r4, r4
47f360d8:	e0a55005 	adc	r5, r5, r5
47f360dc:	e2944001 	adds	r4, r4, #1
47f360e0:	e2a55000 	adc	r5, r5, #0
47f360e4:	ea000001 	b	0x47f360f0
47f360e8:	e0944004 	adds	r4, r4, r4
47f360ec:	e0a55005 	adc	r5, r5, r5
47f360f0:	e2566001 	subs	r6, r6, #1
47f360f4:	1afffff1 	bne	0x47f360c0
47f360f8:	e0948000 	adds	r8, r4, r0
47f360fc:	e1a02007 	mov	r2, r7
47f36100:	e0a59001 	adc	r9, r5, r1
47f36104:	e1a00004 	mov	r0, r4
47f36108:	e1a01005 	mov	r1, r5
47f3610c:	ebffff29 	bl	0x47f35db8
47f36110:	e1a02007 	mov	r2, r7
47f36114:	ebffff35 	bl	0x47f35df0
47f36118:	e0580000 	subs	r0, r8, r0
47f3611c:	e0c91001 	sbc	r1, r9, r1
47f36120:	e8bd83f8 	pop	{r3, r4, r5, r6, r7, r8, r9, pc}
47f36124:	e3a00000 	mov	r0, #0
47f36128:	e3a01000 	mov	r1, #0
47f3612c:	e8bd83f8 	pop	{r3, r4, r5, r6, r7, r8, r9, pc}
47f36130:	47f3ac15 			@ <UNDEFINED> instruction: 0x47f3ac15
47f36134:	47f3ac1d 			@ <UNDEFINED> instruction: 0x47f3ac1d
47f36138:	47f3ac24 	ldrbmi	r10, [r3, r4, lsr #24]!
47f3613c:	47f3ac2b 	ldrbmi	r10, [r3, r11, lsr #24]!
47f36140:	47f3ac32 			@ <UNDEFINED> instruction: 0x47f3ac32
47f36144:	47f3ac39 			@ <UNDEFINED> instruction: 0x47f3ac39
47f36148:	47f3ac40 	ldrbmi	r10, [r3, r0, asr #24]!
47f3614c:	47f3ac47 	ldrbmi	r10, [r3, r7, asr #24]!
47f36150:	47f3ac4e 	ldrbmi	r10, [r3, lr, asr #24]!
47f36154:	47f3ac55 	ubfxmi	r10, r5, #24, #20
47f36158:	47f3ac5c 	ubfxmi	r10, r12, #24, #20
47f3615c:	47f3ac64 	ldrbmi	r10, [r3, r4, ror #24]!
47f36160:	47f3ac6c 	ldrbmi	r10, [r3, r12, ror #24]!
47f36164:	47f3ac74 			@ <UNDEFINED> instruction: 0x47f3ac74
47f36168:	47f3ac7c 			@ <UNDEFINED> instruction: 0x47f3ac7c
47f3616c:	47f3ac84 	ldrbmi	r10, [r3, r4, lsl #25]!
47f36170:	47f3ac8c 	ldrbmi	r10, [r3, r12, lsl #25]!
47f36174:	47f3ac94 			@ <UNDEFINED> instruction: 0x47f3ac94
47f36178:	47f3ac9b 			@ <UNDEFINED> instruction: 0x47f3ac9b
47f3617c:	47f3aca2 	ldrbmi	r10, [r3, r2, lsr #25]!
47f36180:	47f3aca9 	ldrbmi	r10, [r3, r9, lsr #25]!
47f36184:	47f3acb0 			@ <UNDEFINED> instruction: 0x47f3acb0
47f36188:	47f3acb7 			@ <UNDEFINED> instruction: 0x47f3acb7
47f3618c:	47f3acbe 			@ <UNDEFINED> instruction: 0x47f3acbe
47f36190:	47f3acc5 	ldrbmi	r10, [r3, r5, asr #25]!
47f36194:	47f3accc 	ldrbmi	r10, [r3, r12, asr #25]!
47f36198:	47f3acd3 	ubfxmi	r10, r3, #25, #20
47f3619c:	47f3acdb 	ubfxmi	r10, r11, #25, #20
47f361a0:	47f3ace2 	ldrbmi	r10, [r3, r2, ror #25]!
47f361a4:	47f3acea 	ldrbmi	r10, [r3, r10, ror #25]!
47f361a8:	47f3acf2 			@ <UNDEFINED> instruction: 0x47f3acf2
47f361ac:	47f3acfa 			@ <UNDEFINED> instruction: 0x47f3acfa
47f361b0:	428a2f98 	addmi	r2, r10, #152, 30	@ 0x260
47f361b4:	71374491 	teqvc	r7, r1	@ <illegal shifter operand>
47f361b8:	b5c0fbcf 	strblt	pc, [r0, #3023]	@ 0xbcf	@ <UNPREDICTABLE>
47f361bc:	e9b5dba5 	ldmib	r5!, {r0, r2, r5, r7, r8, r9, r11, r12, lr, pc}
47f361c0:	3956c25b 	ldmdbcc	r6, {r0, r1, r3, r4, r6, r9, lr, pc}^
47f361c4:	59f111f1 	ldmibpl	r1!, {r0, r4, r5, r6, r7, r8, r12}^
47f361c8:	923f82a4 	eorsls	r8, pc, #164, 4	@ 0x4000000a
47f361cc:	ab1c5ed5 	blge	0x4864dd28
47f361d0:	d807aa98 	stmdale	r7, {r3, r4, r7, r9, r11, sp, pc}
47f361d4:	12835b01 	addne	r5, r3, #1024	@ 0x400
47f361d8:	243185be 	ldrtcs	r8, [r1], #-1470	@ 0xfffffa42
47f361dc:	550c7dc3 	strpl	r7, [r12, #-3523]	@ 0xfffff23d
47f361e0:	72be5d74 	adcsvc	r5, lr, #116, 26	@ 0x1d00
47f361e4:	80deb1fe 	ldrshhi	r11, [lr], #30
47f361e8:	9bdc06a7 	blls	0x47637c8c
47f361ec:	c19bf174 	orrsgt	pc, r11, r4, ror r1	@ <UNPREDICTABLE>
47f361f0:	e49b69c1 	ldr	r6, [r11], #2497	@ 0x9c1
47f361f4:	efbe4786 	svc	0x00be4786
47f361f8:	0fc19dc6 	svceq	0x00c19dc6
47f361fc:	240ca1cc 	strcs	r10, [r12], #-460	@ 0xfffffe34
