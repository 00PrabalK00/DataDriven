%M2_FEASIBILITY Milestone 2: go/no-go feasibility sweep over aerodynamic assumptions (L2).
run(fullfile(fileparts(mfilename('fullpath')), 'setupPaths.m'));
[D, info] = chute.doe.lhsDesigns(16, 1);
rep = chute.ode.feasibilitySweep(designs=D);
disp(rep.evidence);
fprintf('fraction of assumption sets where best-vs-worst design is resolvable: %.2f\n', rep.fractionResolvable);
fprintf('  at placeholder mass 0.15 kg / height 2.5 m: %.2f\n', rep.fractionResolvableAtPlaceholders);
fprintf('  if slits have no aerodynamic effect: %.2f\n', rep.slitOnlyResolvable);
