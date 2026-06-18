package fr.inria.astor.approaches.cardumen;

import java.util.Date;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import com.martiansoftware.jsap.JSAPException;

import fr.inria.astor.approaches.jgenprog.JGenProg;
import fr.inria.astor.core.entities.ProgramVariant;
import fr.inria.astor.core.manipulation.MutationSupporter;
import fr.inria.astor.core.manipulation.filters.TargetElementProcessor;
import fr.inria.astor.core.setup.ConfigurationProperties;
import fr.inria.astor.core.setup.ProjectRepairFacade;
import fr.inria.astor.core.solutionsearch.spaces.ingredients.scopes.ExpressionClassTypeIngredientSpace;
import fr.inria.astor.core.solutionsearch.spaces.ingredients.scopes.ExpressionTypeIngredientSpace;
import fr.inria.astor.core.solutionsearch.spaces.ingredients.scopes.IngredientPoolScope;
import fr.inria.astor.core.stats.PatchStat;
import fr.inria.astor.core.stats.PatchStat.PatchStatEnum;
import fr.inria.astor.core.stats.Stats;
import fr.inria.astor.core.stats.Stats.GeneralStatEnum;
import fr.inria.main.ExecutionResult;
import fr.inria.main.evolution.ExtensionPoints;

/**
 * 
 * @author Matias Martinez
 *
 */
public class CardumenApproach extends JGenProg {

	public CardumenApproach(MutationSupporter mutatorExecutor, ProjectRepairFacade projFacade) throws JSAPException {
		super(mutatorExecutor, projFacade);
		// Default configuration of Cardumen:
		ConfigurationProperties.setProperty("cleantemplates", "true");

		if (!ConfigurationProperties.hasProperty(ExtensionPoints.INGREDIENT_TRANSFORM_STRATEGY.identifier)) {

			if (ConfigurationProperties.getPropertyBool("probabilistictransformation")) {
				ConfigurationProperties.setProperty(ExtensionPoints.INGREDIENT_TRANSFORM_STRATEGY.identifier,
						"name-probability-based");
			} else
				ConfigurationProperties.setProperty(ExtensionPoints.INGREDIENT_TRANSFORM_STRATEGY.identifier,
						"random-variable-replacement");
		}

		ConfigurationProperties.setProperty(ExtensionPoints.TARGET_CODE_PROCESSOR.identifier, "expression");
		ConfigurationProperties.setProperty(ExtensionPoints.OPERATORS_SPACE.identifier, "r-expression");
		setPropertyIfNotDefined(ExtensionPoints.INGREDIENT_SEARCH_STRATEGY.identifier, "name-probability-based");

	}

	@Override
	protected void loadIngredientPool() throws JSAPException, Exception {
		List<TargetElementProcessor<?>> ingredientProcessors = this.getTargetElementProcessors();
		ExpressionTypeIngredientSpace ingredientspace = ((ConfigurationProperties.getPropertyBool("uniformreplacement"))
				? new ExpressionClassTypeIngredientSpace(ingredientProcessors)
				: new ExpressionTypeIngredientSpace(ingredientProcessors));
		String scope = ConfigurationProperties.getProperty(ExtensionPoints.INGREDIENT_STRATEGY_SCOPE.identifier);
		if (scope != null) {
			ingredientspace.scope = IngredientPoolScope.valueOf(scope.toUpperCase());
		}
		this.setIngredientPool(ingredientspace);
	}

	/** Candidate number (1-based, in tested order) at which each solution variant was found, by variant id. */
	private final Map<Integer, Integer> candidateNumberByVariantId = new HashMap<>();

	/**
	 * Counts every candidate that reaches compile/validation, accumulated across all
	 * modification points. This is the single choke point through which both the normal
	 * Cardumen evolutionary loop and {@link CardumenExportEngine} test a candidate.
	 * <p>
	 * When the candidate turns out to be a patch, records which candidate number it was
	 * and logs it together with the elapsed time since the search started.
	 */
	@Override
	public boolean processCreatedVariant(ProgramVariant programVariant, int generation) throws Exception {
		Stats.currentStat.increment(GeneralStatEnum.NR_TESTED_CANDIDATES);
		boolean found = super.processCreatedVariant(programVariant, generation);
		if (found) {
			int candidateNumber = testedCandidateCount();
			double elapsed = (System.currentTimeMillis() - dateInitEvolution.getTime()) / 1000d;
			candidateNumberByVariantId.put(programVariant.getId(), candidateNumber);
			log.info("Cardumen: patch found at candidate #" + candidateNumber + " after " + elapsed
					+ "s (variant " + programVariant.getId() + ")");
		}
		return found;
	}

	/** Current value of the tested-candidates counter (0 if not yet initialised). */
	private int testedCandidateCount() {
		Object c = Stats.currentStat.getGeneralStats().get(GeneralStatEnum.NR_TESTED_CANDIDATES);
		return (c instanceof Stats.Counter) ? ((Stats.Counter) c).getCounter() : 0;
	}

	/**
	 * Attaches the candidate number to each found patch's stats. The elapsed
	 * timestamp is already recorded by the superclass as {@link PatchStatEnum#TIME}.
	 */
	@Override
	public List<PatchStat> createStatsForPatches(List<ProgramVariant> variants, int generation, Date dateInitEvolution) {
		List<PatchStat> patches = super.createStatsForPatches(variants, generation, dateInitEvolution);
		for (ProgramVariant v : variants) {
			Integer num = candidateNumberByVariantId.get(v.getId());
			if (num != null && v.getPatchInfo() != null) {
				v.getPatchInfo().addStat(PatchStatEnum.CANDIDATE_NUMBER, num);
			}
		}
		return patches;
	}

	/**
	 * Surfaces the two Cardumen performance measurements at the end of a run: the total
	 * number of candidates tested and the total runtime. Both are also present in the
	 * standard stats output ({@code NR_TESTED_CANDIDATES} and {@code TOTAL_TIME}).
	 */
	@Override
	public ExecutionResult atEnd() {
		ExecutionResult result = super.atEnd();
		Object tested = Stats.currentStat.getGeneralStats().get(GeneralStatEnum.NR_TESTED_CANDIDATES);
		Object time = Stats.currentStat.getGeneralStats().get(GeneralStatEnum.TOTAL_TIME);
		log.info("Cardumen: total candidates tested = " + (tested != null ? tested : 0));
		log.info("Cardumen: total runtime (s) = " + time);
		return result;
	}

}
